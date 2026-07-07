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
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    value = str(value).strip().upper()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
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
        # DBF numeric fields may arrive as ints/floats
        if re.fullmatch(r"\d+(\.0)?", text):
            text = str(int(float(text)))
        return text
    except Exception:
        return str(value).strip()


def transform_geometry(geom, transformer):
    """
    Transform a GeoJSON-like geometry from EPSG:27700 to EPSG:4326.
    pyshp provides __geo_interface__ geometries.
    """
    def transform_coords(coords):
        if isinstance(coords, (list, tuple)) and len(coords) == 2 and all(
            isinstance(x, (int, float)) for x in coords
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
    parser.add_argument("--geojson-output-dir", required=True)
    parser.add_argument("--outputs-dir", required=True)
    parser.add_argument("--github-raw-base-url", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    shp_path = input_dir / f"{args.basename}.shp"

    geojson_output_dir = Path(args.geojson_output_dir)
    outputs_dir = Path(args.outputs_dir)

    geojson_output_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    schools = pd.read_csv(args.schools_csv)
    lookup = pd.read_csv(args.lookup_csv)

    # Ensure expected columns exist
    required_school_cols = ["SchoolName", "PostCode_clean", "LAName", "SeedCode"]
    missing_school_cols = [c for c in required_school_cols if c not in schools.columns]
    if missing_school_cols:
        raise ValueError(f"Missing columns in schools CSV: {missing_school_cols}")

    required_lookup_cols = ["SchoolKey", "CatchmentGeoJsonUrl", "FallbackGeoJsonUrl"]
    missing_lookup_cols = [c for c in required_lookup_cols if c not in lookup.columns]
    if missing_lookup_cols:
        raise ValueError(f"Missing columns in lookup CSV: {missing_lookup_cols}")

    schools["SeedCode_clean"] = schools["SeedCode"].apply(clean_seed)
    schools["SchoolName_norm"] = schools["SchoolName"].apply(norm_text)
    schools["LAName_norm"] = schools["LAName"].apply(norm_text)
    schools["SchoolKey"] = schools["SchoolName"].astype(str).str.strip() + "|" + schools["PostCode_clean"].astype(str).str.strip()

    # Matching dictionaries
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

    reader = shapefile.Reader(str(shp_path))
    fields = [f[0] for f in reader.fields[1:]]

    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

    match_rows = []
    index_rows = []
    url_updates = {}

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

        # 1. Seed code match
        if source_seed and source_seed in seed_to_keys:
            keys = seed_to_keys[source_seed]
            match_count = len(keys)
            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "seed_code"
            else:
                matched_method = "seed_code_multiple"

        # 2. School name + local authority
        if not matched_school_key:
            keys = name_la_to_keys.get((source_school_norm, source_la_norm), [])
            match_count = len(keys)
            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "school_name_and_la"
            elif len(keys) > 1:
                matched_method = "school_name_and_la_multiple"

        # 3. School name only
        if not matched_school_key:
            keys = name_to_keys.get(source_school_norm, [])
            match_count = len(keys)
            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "school_name_only"
            elif len(keys) > 1:
                matched_method = "school_name_only_multiple"

        filename_base = slugify(
            f"scotland_sn_{source_local_auth}_{source_school_name}_{source_seed or idx}"
        )
        filename = f"{filename_base}.geojson"

        if filename in filename_counter:
            filename_counter[filename] += 1
            filename = f"{filename_base}_{filename_counter[filename]}.geojson"
        else:
            filename_counter[filename] = 1

        geojson_url = args.github_raw_base_url.rstrip("/") + "/" + filename

        geom = shape_record.shape.__geo_interface__
        transformed_geom = transform_geometry(geom, transformer)

        feature_props = {
            "source_school_nam": source_school_name,
            "source_local_auth": source_local_auth,
            "source_la_s_code": props.get("la_s_code", ""),
            "source_seed_code": source_seed,
            "source_type": props.get("type", ""),
            "source_level": props.get("level", ""),
            "matched_school_key": matched_school_key,
            "matched_method": matched_method,
            "catchment_layer": "Scotland secondary non-denominational",
        }

        fc = {
            "type": "FeatureCollection",
            "name": filename.replace(".geojson", ""),
            "features": [
                {
                    "type": "Feature",
                    "geometry": transformed_geom,
                    "properties": feature_props,
                }
            ],
        }

        out_path = geojson_output_dir / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))

        if matched_school_key:
            url_updates[matched_school_key] = geojson_url

        match_rows.append(
            {
                "source_row": idx,
                "source_school_nam": source_school_name,
                "source_local_auth": source_local_auth,
                "source_seed_code": source_seed,
                "matched_school_key": matched_school_key,
                "matched_method": matched_method,
                "match_count": match_count,
                "geojson_filename": filename,
                "geojson_url": geojson_url,
            }
        )

        index_rows.append(
            {
                "geojson_filename": filename,
                "geojson_url": geojson_url,
                "source_school_nam": source_school_name,
                "source_local_auth": source_local_auth,
                "source_seed_code": source_seed,
                "matched_school_key": matched_school_key,
                "matched_method": matched_method,
            }
        )

    match_df = pd.DataFrame(match_rows)
    index_df = pd.DataFrame(index_rows)

    # Update lookup
    updated_lookup = lookup.copy()

    if "HasRealCatchmentGeoJson" not in updated_lookup.columns:
        updated_lookup["HasRealCatchmentGeoJson"] = False

    def update_url(row):
        key = row["SchoolKey"]
        if key in url_updates:
            return url_updates[key]
        return row.get("CatchmentGeoJsonUrl", "")

    updated_lookup["CatchmentGeoJsonUrl"] = updated_lookup.apply(update_url, axis=1)
    updated_lookup["HasRealCatchmentGeoJson"] = updated_lookup["CatchmentGeoJsonUrl"].astype(str).str.len() > 0

    # Preserve __ALL__ as no real catchment
    updated_lookup.loc[updated_lookup["SchoolKey"].eq("__ALL__"), "CatchmentGeoJsonUrl"] = ""
    updated_lookup.loc[updated_lookup["SchoolKey"].eq("__ALL__"), "HasRealCatchmentGeoJson"] = False

    # Save outputs
    updated_lookup_path = outputs_dir / "school_reference_layer_lookup_plus_scotland_sn.csv"
    match_review_path = outputs_dir / "scotland_sn_catchment_match_review.csv"
    index_path = outputs_dir / "scotland_sn_catchment_geojson_index.csv"
    summary_path = outputs_dir / "processing_summary.md"

    updated_lookup.to_csv(updated_lookup_path, index=False)
    match_df.to_csv(match_review_path, index=False)
    index_df.to_csv(index_path, index=False)

    matched_count = int(match_df["matched_school_key"].astype(str).str.len().gt(0).sum())
    unmatched_count = int(len(match_df) - matched_count)
    seed_matches = int((match_df["matched_method"] == "seed_code").sum())
    name_la_matches = int((match_df["matched_method"] == "school_name_and_la").sum())
    name_only_matches = int((match_df["matched_method"] == "school_name_only").sum())

    summary = f"""# Scotland Secondary Non-Denominational Catchment Processing Summary

## Inputs

- Shapefile: `{shp_path}`
- Schools CSV: `{args.schools_csv}`
- Lookup CSV: `{args.lookup_csv}`

## Outputs

- Split GeoJSON folder: `{geojson_output_dir}`
- Updated lookup: `{updated_lookup_path}`
- Match review: `{match_review_path}`
- GeoJSON index: `{index_path}`

## Counts

- Catchment records processed: `{len(match_df)}`
- GeoJSON files created: `{len(index_df)}`
- Matched catchments: `{matched_count}`
- Unmatched catchments: `{unmatched_count}`
- Seed-code matches: `{seed_matches}`
- School name + LA matches: `{name_la_matches}`
- School name only matches: `{name_only_matches}`
- Lookup rows with real catchment URL after update: `{int(updated_lookup["HasRealCatchmentGeoJson"].sum())}`

## Notes

The source shapefile is assumed to be EPSG:27700 British National Grid and is transformed to EPSG:4326 for GeoJSON output.
"""

    summary_path.write_text(summary, encoding="utf-8")

    print(summary)


if __name__ == "__main__":
    main()
