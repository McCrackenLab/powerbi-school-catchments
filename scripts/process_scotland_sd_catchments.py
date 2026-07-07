import argparse
import json
import math
import re
import unicodedata
from pathlib import Path

import pandas as pd
import shapefile
from pyproj import Transformer


def slugify(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value or "unknown"


def norm_text(value):
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    value = str(value).strip().upper()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")

    value = value.replace(" WEF AUG 23", "")
    value = value.replace(" SECONDARY SCHOOL", " HIGH SCHOOL")
    value = value.replace(" SECONDARY", " HIGH SCHOOL")
    value = value.replace(" COMMUNITY HIGH SCHOOL", " HIGH SCHOOL")
    value = value.replace(" COMMUNITY SCHOOL", " SCHOOL")
    value = value.replace(" GRAMMAR CAMPUS", " GRAMMAR SCHOOL")

    value = value.replace(" R C ", " RC ")
    value = value.replace(" R.C. ", " RC ")
    value = value.replace(" ROMAN CATHOLIC ", " RC ")

    if re.search(r"\bHIGH$", value):
        value = value + " SCHOOL"

    if re.search(r"\bGRAMMAR$", value):
        value = value + " SCHOOL"

    value = re.sub(r"[^A-Z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def clean_seed(value):
    if value is None:
        return ""

    try:
        if isinstance(value, float) and math.isnan(value):
            return ""

        text = str(value).strip()

        if text == "":
            return ""

        if text.endswith(".0"):
            text = text[:-2]

        if re.fullmatch(r"\d+(\.0)?", text):
            text = str(int(float(text)))

        return text

    except Exception:
        return str(value).strip()


def transform_geometry(geom, transformer):
    def transform_coords(coords):
        if (
            isinstance(coords, (list, tuple))
            and len(coords) == 2
            and all(isinstance(x, (int, float)) for x in coords)
        ):
            x, y = coords
            lon, lat = transformer.transform(x, y)
            return [lon, lat]

        return [transform_coords(c) for c in coords]

    return {
        "type": geom["type"],
        "coordinates": transform_coords(geom["coordinates"]),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--basename", required=True)
    parser.add_argument("--schools-csv", required=True)
    parser.add_argument("--lookup-csv", required=True)
    parser.add_argument("--manual-overrides-csv", required=False, default="")
    parser.add_argument("--geojson-output-dir", required=True)
    parser.add_argument("--outputs-dir", required=True)
    parser.add_argument("--github-raw-base-url", required=True)

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    shp_path = input_dir / f"{args.basename}.shp"

    geojson_output_dir = Path(args.geojson_output_dir)
    combined_output_dir = geojson_output_dir / "combined-by-school"
    outputs_dir = Path(args.outputs_dir)

    geojson_output_dir.mkdir(parents=True, exist_ok=True)
    combined_output_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if not shp_path.exists():
        raise FileNotFoundError(f"Shapefile not found: {shp_path}")

    schools = pd.read_csv(args.schools_csv)
    lookup = pd.read_csv(args.lookup_csv)

    manual_overrides = pd.DataFrame()

    if args.manual_overrides_csv:
        manual_overrides_path = Path(args.manual_overrides_csv)
        if manual_overrides_path.exists():
            manual_overrides = pd.read_csv(manual_overrides_path)
        else:
            print(f"Manual overrides file not found, continuing without overrides: {manual_overrides_path}")

    required_school_cols = [
        "SchoolName",
        "PostCode_clean",
        "LAName",
        "SeedCode",
    ]

    missing_school_cols = [
        c for c in required_school_cols
        if c not in schools.columns
    ]

    if missing_school_cols:
        raise ValueError(f"Missing columns in schools CSV: {missing_school_cols}")

    required_lookup_cols = [
        "SchoolKey",
        "CatchmentGeoJsonUrl",
        "FallbackGeoJsonUrl",
    ]

    missing_lookup_cols = [
        c for c in required_lookup_cols
        if c not in lookup.columns
    ]

    if missing_lookup_cols:
        raise ValueError(f"Missing columns in lookup CSV: {missing_lookup_cols}")

    schools["SeedCode_clean"] = schools["SeedCode"].apply(clean_seed)
    schools["SchoolName_norm"] = schools["SchoolName"].apply(norm_text)
    schools["LAName_norm"] = schools["LAName"].apply(norm_text)

    schools["SchoolKey"] = (
        schools["SchoolName"].astype(str).str.strip()
        + "|"
        + schools["PostCode_clean"].astype(str).str.strip()
    )

    seed_to_keys = (
        schools[schools["SeedCode_clean"].astype(str).str.len() > 0]
        .groupby("SeedCode_clean")["SchoolKey"]
        .apply(list)
        .to_dict()
    )

    name_la_to_keys = (
        schools.groupby(["SchoolName_norm", "LAName_norm"])["SchoolKey"]
        .apply(list)
        .to_dict()
    )

    name_to_keys = (
        schools.groupby("SchoolName_norm")["SchoolKey"]
        .apply(list)
        .to_dict()
    )

    school_key_to_info = (
        schools.drop_duplicates("SchoolKey")
        .set_index("SchoolKey")
        .to_dict(orient="index")
    )

    manual_override_by_source_row = {}

    if not manual_overrides.empty:
        required_override_cols = [
            "source_row",
            "target_school_name",
            "target_local_auth",
        ]

        missing_override_cols = [
            c for c in required_override_cols
            if c not in manual_overrides.columns
        ]

        if missing_override_cols:
            raise ValueError(
                f"Missing columns in manual overrides CSV: {missing_override_cols}"
            )

        for _, override_row in manual_overrides.iterrows():
            source_row = int(override_row["source_row"])

            target_school_name_norm = norm_text(override_row["target_school_name"])
            target_local_auth_norm = norm_text(override_row["target_local_auth"])

            manual_override_by_source_row[source_row] = {
                "target_school_name": override_row["target_school_name"],
                "target_local_auth": override_row["target_local_auth"],
                "target_school_name_norm": target_school_name_norm,
                "target_local_auth_norm": target_local_auth_norm,
                "override_reason": override_row.get("override_reason", ""),
            }

    reader = shapefile.Reader(str(shp_path))
    fields = [f[0] for f in reader.fields[1:]]

    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

    match_rows = []
    row_index_rows = []
    combined_index_rows = []

    features_by_school_key = {}
    row_urls_by_school_key = {}

    filename_counter = {}

    for idx, shape_record in enumerate(reader.iterShapeRecords(), start=1):
        rec_values = list(shape_record.record)
        props = dict(zip(fields, rec_values))

        source_school_name = str(props.get("school_nam", "")).strip()
        source_local_auth = str(props.get("local_auth", "")).strip()
        source_seed = clean_seed(props.get("seed_code"))

        source_school_norm = norm_text(source_school_name)
        source_la_norm = norm_text(source_local_auth)

        matched_school_key = ""
        matched_method = "unmatched"
        match_count = 0
        manual_override_reason = ""

        manual_override = manual_override_by_source_row.get(idx)

        if manual_override:
            override_keys = name_la_to_keys.get(
                (
                    manual_override["target_school_name_norm"],
                    manual_override["target_local_auth_norm"],
                ),
                [],
            )

            match_count = len(override_keys)
            manual_override_reason = manual_override.get("override_reason", "")

            if len(override_keys) == 1:
                matched_school_key = override_keys[0]
                matched_method = "manual_override"
            elif len(override_keys) > 1:
                matched_method = "manual_override_multiple"
            else:
                matched_method = "manual_override_target_not_found"

        if not matched_school_key and source_seed and source_seed in seed_to_keys:
            keys = seed_to_keys[source_seed]
            match_count = len(keys)

            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "seed_code"
            else:
                matched_method = "seed_code_multiple"

        if not matched_school_key:
            keys = name_la_to_keys.get((source_school_norm, source_la_norm), [])
            match_count = len(keys)

            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "school_name_and_la"
            elif len(keys) > 1:
                matched_method = "school_name_and_la_multiple"

        if not matched_school_key:
            keys = name_to_keys.get(source_school_norm, [])
            match_count = len(keys)

            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "school_name_only"
            elif len(keys) > 1:
                matched_method = "school_name_only_multiple"

        filename_base = slugify(
            f"scotland_sd_{source_local_auth}_{source_school_name}_{source_seed or idx}"
        )

        filename = f"{filename_base}.geojson"

        if filename in filename_counter:
            filename_counter[filename] += 1
            filename = f"{filename_base}_{filename_counter[filename]}.geojson"
        else:
            filename_counter[filename] = 1

        row_geojson_url = args.github_raw_base_url.rstrip("/") + "/" + filename

        geom = shape_record.shape.__geo_interface__
        transformed_geom = transform_geometry(geom, transformer)

        feature_props = {
            "source_row": idx,
            "source_school_nam": source_school_name,
            "source_local_auth": source_local_auth,
            "source_la_s_code": props.get("la_s_code", ""),
            "source_seed_code": source_seed,
            "source_type": props.get("type", ""),
            "source_level": props.get("level", ""),
            "matched_school_key": matched_school_key,
            "matched_method": matched_method,
            "manual_override_reason": manual_override_reason,
            "catchment_layer": "Scotland secondary denominational",
        }

        feature = {
            "type": "Feature",
            "geometry": transformed_geom,
            "properties": feature_props,
        }

        row_fc = {
            "type": "FeatureCollection",
            "name": filename.replace(".geojson", ""),
            "features": [feature],
        }

        out_path = geojson_output_dir / filename

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(row_fc, f, ensure_ascii=False, separators=(",", ":"))

        if matched_school_key:
            features_by_school_key.setdefault(matched_school_key, []).append(feature)
            row_urls_by_school_key.setdefault(matched_school_key, []).append(row_geojson_url)

        match_rows.append(
            {
                "source_row": idx,
                "source_school_nam": source_school_name,
                "source_local_auth": source_local_auth,
                "source_seed_code": source_seed,
                "matched_school_key": matched_school_key,
                "matched_method": matched_method,
                "match_count": match_count,
                "manual_override_reason": manual_override_reason,
                "geojson_filename": filename,
                "geojson_url": row_geojson_url,
            }
        )

        row_index_rows.append(
            {
                "geojson_filename": filename,
                "geojson_url": row_geojson_url,
                "source_school_nam": source_school_name,
                "source_local_auth": source_local_auth,
                "source_seed_code": source_seed,
                "matched_school_key": matched_school_key,
                "matched_method": matched_method,
            }
        )

    combined_url_updates = {}

    for school_key, features in features_by_school_key.items():
        info = school_key_to_info.get(school_key, {})
        school_name = str(info.get("SchoolName", school_key.split("|")[0])).strip()
        postcode = str(info.get("PostCode_clean", school_key.split("|")[-1])).strip()
        local_authority = str(info.get("LAName", "")).strip()

        combined_filename = (
            "scotland_sd_combined_"
            + slugify(f"{local_authority}_{school_name}_{postcode}")
            + ".geojson"
        )

        combined_url = (
            args.github_raw_base_url.rstrip("/")
            + "/combined-by-school/"
            + combined_filename
        )

        combined_fc = {
            "type": "FeatureCollection",
            "name": combined_filename.replace(".geojson", ""),
            "features": features,
            "properties": {
                "matched_school_key": school_key,
                "school_name": school_name,
                "school_postcode": postcode,
                "local_authority": local_authority,
                "catchment_layer": "Scotland secondary denominational",
                "feature_count": len(features),
            },
        }

        combined_path = combined_output_dir / combined_filename

        with open(combined_path, "w", encoding="utf-8") as f:
            json.dump(combined_fc, f, ensure_ascii=False, separators=(",", ":"))

        combined_url_updates[school_key] = combined_url

        combined_index_rows.append(
            {
                "matched_school_key": school_key,
                "school_name": school_name,
                "school_postcode": postcode,
                "local_authority": local_authority,
                "combined_geojson_filename": combined_filename,
                "combined_geojson_url": combined_url,
                "feature_count": len(features),
                "row_geojson_urls": " | ".join(row_urls_by_school_key.get(school_key, [])),
            }
        )

    match_df = pd.DataFrame(match_rows)
    row_index_df = pd.DataFrame(row_index_rows)
    combined_index_df = pd.DataFrame(combined_index_rows)

    updated_lookup = lookup.copy()

    if "HasRealCatchmentGeoJson" not in updated_lookup.columns:
        updated_lookup["HasRealCatchmentGeoJson"] = False

    def update_url(row):
        key = row["SchoolKey"]

        if key in combined_url_updates:
            return combined_url_updates[key]

        return row.get("CatchmentGeoJsonUrl", "")

    updated_lookup["CatchmentGeoJsonUrl"] = updated_lookup.apply(update_url, axis=1)

    updated_lookup["HasRealCatchmentGeoJson"] = (
        updated_lookup["CatchmentGeoJsonUrl"]
        .fillna("")
        .astype(str)
        .str.len()
        > 0
    )

    updated_lookup.loc[
        updated_lookup["SchoolKey"].eq("__ALL__"),
        "CatchmentGeoJsonUrl",
    ] = ""

    updated_lookup.loc[
        updated_lookup["SchoolKey"].eq("__ALL__"),
        "HasRealCatchmentGeoJson",
    ] = False

    updated_lookup_path = outputs_dir / "school_reference_layer_lookup_plus_scotland_sn_sd.csv"
    match_review_path = outputs_dir / "scotland_sd_catchment_match_review.csv"
    row_index_path = outputs_dir / "scotland_sd_catchment_geojson_index.csv"
    combined_index_path = outputs_dir / "scotland_sd_combined_by_school_index.csv"
    summary_path = outputs_dir / "processing_summary.md"

    updated_lookup.to_csv(updated_lookup_path, index=False)
    match_df.to_csv(match_review_path, index=False)
    row_index_df.to_csv(row_index_path, index=False)
    combined_index_df.to_csv(combined_index_path, index=False)

    matched_count = int(match_df["matched_school_key"].fillna("").astype(str).str.len().gt(0).sum())
    unmatched_count = int(len(match_df) - matched_count)

    seed_matches = int((match_df["matched_method"] == "seed_code").sum())
    manual_override_matches = int((match_df["matched_method"] == "manual_override").sum())
    manual_override_target_not_found = int((match_df["matched_method"] == "manual_override_target_not_found").sum())
    manual_override_multiple = int((match_df["matched_method"] == "manual_override_multiple").sum())
    name_la_matches = int((match_df["matched_method"] == "school_name_and_la").sum())
    name_only_matches = int((match_df["matched_method"] == "school_name_only").sum())

    combined_school_count = len(combined_index_df)
    multi_feature_school_count = int((combined_index_df["feature_count"] > 1).sum()) if len(combined_index_df) else 0
    lookup_real_count = int(updated_lookup["HasRealCatchmentGeoJson"].sum())

    summary = f"""# Scotland Secondary Denominational Catchment Processing Summary

## Inputs

- Shapefile: `{shp_path}`
- Schools CSV: `{args.schools_csv}`
- Lookup CSV: `{args.lookup_csv}`
- Manual overrides CSV: `{args.manual_overrides_csv}`

## Outputs

- Row-level GeoJSON folder: `{geojson_output_dir}`
- Combined per-school GeoJSON folder: `{combined_output_dir}`
- Updated lookup: `{updated_lookup_path}`
- Match review: `{match_review_path}`
- Row-level GeoJSON index: `{row_index_path}`
- Combined per-school GeoJSON index: `{combined_index_path}`

## Counts

- Catchment records processed: `{len(match_df)}`
- Row-level GeoJSON files created: `{len(row_index_df)}`
- Combined per-school GeoJSON files created: `{combined_school_count}`
- Schools with multiple denominational catchment features: `{multi_feature_school_count}`
- Matched catchments: `{matched_count}`
- Unmatched catchments: `{unmatched_count}`
- Seed-code matches: `{seed_matches}`
- Manual override matches: `{manual_override_matches}`
- Manual override target not found: `{manual_override_target_not_found}`
- Manual override multiple matches: `{manual_override_multiple}`
- School name + LA matches: `{name_la_matches}`
- School name only matches: `{name_only_matches}`
- Lookup rows with real catchment URL after update: `{lookup_real_count}`

## Notes

The source shapefile is assumed to be EPSG:27700 British National Grid and is transformed to EPSG:4326 for GeoJSON output.

Manual overrides are applied before automatic seed-code and name matching.

For every matched school, the lookup now points to a combined per-school GeoJSON file. This avoids losing cross-authority or multi-part denominational catchment polygons when a school appears in more than one source catchment record.
"""

    summary_path.write_text(summary, encoding="utf-8")

    print(summary)


if __name__ == "__main__":
    main()
