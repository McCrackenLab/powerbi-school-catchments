import argparse
import csv
import json
from pathlib import Path

import pandas as pd
import shapefile


def truncate_value(value, max_len=300):
    if value is None:
        return ""
    text = str(value)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--basename", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shp_path = input_dir / f"{args.basename}.shp"
    shx_path = input_dir / f"{args.basename}.shx"
    dbf_path = input_dir / f"{args.basename}.dbf"
    prj_path = input_dir / f"{args.basename}.prj"

    required_files = [shp_path, shx_path, dbf_path]
    missing = [str(p) for p in required_files if not p.exists()]

    report_lines = []
    report_lines.append("# Scotland Secondary Non-Denominational Catchments — Schema Inspection")
    report_lines.append("")
    report_lines.append("## Input files")
    report_lines.append("")

    for extension in ["shp", "shx", "dbf", "prj", "cpg", "cst", "xml"]:
        p = input_dir / f"{args.basename}.{extension}"
        report_lines.append(
            f"- `{p}` — {'found' if p.exists() else 'missing'}"
        )

    if missing:
        report_lines.append("")
        report_lines.append("## Error")
        report_lines.append("")
        report_lines.append("Missing required shapefile components:")
        for p in missing:
            report_lines.append(f"- `{p}`")
        (output_dir / "schema_report.md").write_text("\n".join(report_lines), encoding="utf-8")
        raise FileNotFoundError(f"Missing required files: {missing}")

    reader = shapefile.Reader(str(shp_path))

    fields = reader.fields[1:]  # first field is deletion flag
    records = reader.records()
    shapes = reader.shapes()

    report_lines.append("")
    report_lines.append("## Basic geometry information")
    report_lines.append("")
    report_lines.append(f"- Shape type code: `{reader.shapeType}`")
    report_lines.append(f"- Shape type name: `{reader.shapeTypeName}`")
    report_lines.append(f"- Record count: `{len(records)}`")
    report_lines.append(f"- Shape count: `{len(shapes)}`")
    report_lines.append(f"- Bounding box: `{reader.bbox}`")

    if prj_path.exists():
        prj_text = prj_path.read_text(encoding="utf-8", errors="replace")
    else:
        prj_text = ""

    report_lines.append("")
    report_lines.append("## Projection")
    report_lines.append("")
    if prj_text:
        report_lines.append("```text")
        report_lines.append(prj_text)
        report_lines.append("```")
    else:
        report_lines.append("No `.prj` file found.")

    # Write field schema CSV
    field_rows = []
    for field in fields:
        name, field_type, size, decimal = field
        field_rows.append(
            {
                "field_name": name,
                "field_type": field_type,
                "size": size,
                "decimal": decimal,
            }
        )

    fields_df = pd.DataFrame(field_rows)
    fields_df.to_csv(output_dir / "schema_fields.csv", index=False)

    report_lines.append("")
    report_lines.append("## Fields")
    report_lines.append("")
    report_lines.append("| Field name | Type | Size | Decimal |")
    report_lines.append("|---|---:|---:|---:|")
    for row in field_rows:
        report_lines.append(
            f"| `{row['field_name']}` | `{row['field_type']}` | `{row['size']}` | `{row['decimal']}` |"
        )

    # Candidate matching fields
    candidate_keywords = [
        "name",
        "school",
        "sch",
        "seed",
        "code",
        "denom",
        "catch",
        "la",
        "auth",
        "local",
    ]

    candidate_fields = [
        row["field_name"]
        for row in field_rows
        if any(keyword in row["field_name"].lower() for keyword in candidate_keywords)
    ]

    report_lines.append("")
    report_lines.append("## Candidate matching fields")
    report_lines.append("")
    if candidate_fields:
        for field_name in candidate_fields:
            report_lines.append(f"- `{field_name}`")
    else:
        report_lines.append("No obvious candidate matching fields detected.")

    # Sample records
    field_names = [field[0] for field in fields]
    sample_count = min(30, len(records))

    sample_rows = []
    for i in range(sample_count):
        rec = records[i]
        row = {"sample_row": i + 1}
        for field_name, value in zip(field_names, rec):
            row[field_name] = truncate_value(value)
        sample_rows.append(row)

    sample_df = pd.DataFrame(sample_rows)
    sample_df.to_csv(output_dir / "sample_records.csv", index=False)

    report_lines.append("")
    report_lines.append("## Sample records")
    report_lines.append("")
    report_lines.append(f"Wrote first `{sample_count}` records to:")
    report_lines.append("")
    report_lines.append("```text")
    report_lines.append("outputs/scotland-secondary-non-denom-schema/sample_records.csv")
    report_lines.append("```")

    # Distinct values for candidate fields
    distinct_summary_rows = []

    for field_name in candidate_fields:
        if field_name not in field_names:
            continue

        values = []
        field_index = field_names.index(field_name)
        for rec in records:
            values.append(rec[field_index])

        series = pd.Series(values)
        non_null = series.dropna()
        distinct_values = sorted(set(str(v) for v in non_null if str(v).strip() != ""))

        distinct_summary_rows.append(
            {
                "field_name": field_name,
                "non_blank_count": int(non_null.astype(str).str.strip().ne("").sum()),
                "distinct_count": len(distinct_values),
                "sample_distinct_values": " | ".join(distinct_values[:20]),
            }
        )

        # Write per-field distinct values if manageable
        safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in field_name)
        with open(output_dir / f"distinct_values_{safe_name}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([field_name])
            for value in distinct_values:
                writer.writerow([value])

    pd.DataFrame(distinct_summary_rows).to_csv(
        output_dir / "candidate_field_distinct_summary.csv",
        index=False,
    )

    report_lines.append("")
    report_lines.append("## Candidate field distinct-value summary")
    report_lines.append("")
    report_lines.append("Wrote summary to:")
    report_lines.append("")
    report_lines.append("```text")
    report_lines.append("outputs/scotland-secondary-non-denom-schema/candidate_field_distinct_summary.csv")
    report_lines.append("```")

    # Lightweight JSON metadata too
    metadata = {
        "input_dir": str(input_dir),
        "basename": args.basename,
        "shape_type_code": reader.shapeType,
        "shape_type_name": reader.shapeTypeName,
        "record_count": len(records),
        "shape_count": len(shapes),
        "bbox": reader.bbox,
        "field_names": field_names,
        "candidate_fields": candidate_fields,
        "projection_wkt": prj_text,
    }

    (output_dir / "schema_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    (output_dir / "schema_report.md").write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    print("Schema inspection complete.")
    print(f"Records: {len(records)}")
    print(f"Shape type: {reader.shapeTypeName}")
    print(f"Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
