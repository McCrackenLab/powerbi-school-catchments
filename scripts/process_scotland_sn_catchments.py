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

    # Normalise common school-name variants
    value = value.replace(" WEF AUG 23", "")
    value = value.replace(" SECONDARY SCHOOL", " HIGH SCHOOL")
    value = value.replace(" SECONDARY", " HIGH SCHOOL")
    value = value.replace(" COMMUNITY HIGH SCHOOL", " HIGH SCHOOL")
    value = value.replace(" COMMUNITY SCHOOL", " SCHOOL")
    value = value.replace(" GRAMMAR CAMPUS", " GRAMMAR SCHOOL")

    if re.search(r"\bHIGH$", value):
        value = value + " SCHOOL"

    if re.search(r"\bGRAMMAR$", value):
        value = value + " SCHOOL"

    value = value.replace("THE ROYAL HIGH HIGH SCHOOL", "THE ROYAL HIGH SCHOOL")

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
    """
    Transform a GeoJSON-like geometry from EPSG:27700 to EPSG:4326.
    pyshp provides __geo_interface__ geometries.
    """

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
    outputs_dir = Path(args.outputs_dir)

    geojson_output_dir.mkdir(parents=True, exist_ok=True)
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
        manual_override_reason = ""

        # 0. Manual override match
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

        # 1. Seed-code match
        if not matched_school_key and source_seed and source_seed in seed_to_keys:
            keys = seed_to_keys[source_seed]
            match_count = len(keys)

            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "seed_code"
            else:
                matched_method = "seed_code_multiple"

        # 2. School name + local authority match
        if not matched_school_key:
            keys = name_la_to_keys.get((source_school_norm, source_la_norm), [])
            match_count = len(keys)

            if len(keys) == 1:
                matched_school_key = keys[0]
                matched_method = "school_name_and_la"
            elif len(keys) > 1:
                matched_method = "school_name_and_la_multiple"

        # 3. School name only match
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

