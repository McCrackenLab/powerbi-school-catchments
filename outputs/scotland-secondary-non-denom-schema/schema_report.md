# Scotland Secondary Non-Denominational Catchments — Schema Inspection

## Input files

- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.shp` — found
- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.shx` — found
- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.dbf` — found
- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.prj` — found
- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.cpg` — missing
- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.cst` — found
- `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.xml` — missing

## Basic geometry information

- Shape type code: `5`
- Shape type name: `POLYGON`
- Record count: `324`
- Shape count: `324`
- Bounding box: `BBox(xmin=61135.44049799489, ymin=530212.2716679329, xmax=470332.00371450756, ymax=1220301.501584022)`

## Projection

```text
PROJCS["OSGB 1936 / British National Grid", GEOGCS["OSGB 1936", DATUM["OSGB 1936", SPHEROID["Airy 1830", 6377563.396, 299.3249646, AUTHORITY["EPSG","7001"]], TOWGS84[446.448, -125.157, 542.06, 0.15, 0.247, 0.842, -20.489], AUTHORITY["EPSG","6277"]], PRIMEM["Greenwich", 0.0, AUTHORITY["EPSG","8901"]], UNIT["degree", 0.017453292519943295], AXIS["Geodetic latitude", NORTH], AXIS["Geodetic longitude", EAST], AUTHORITY["EPSG","4277"]], PROJECTION["Transverse_Mercator", AUTHORITY["EPSG","9807"]], PARAMETER["central_meridian", -2.0], PARAMETER["latitude_of_origin", 49.0], PARAMETER["scale_factor", 0.9996012717], PARAMETER["false_easting", 400000.0], PARAMETER["false_northing", -100000.0], UNIT["m", 1.0], AXIS["Easting", EAST], AXIS["Northing", NORTH], AUTHORITY["EPSG","27700"]]
```

## Fields

| Field name | Type | Size | Decimal |
|---|---:|---:|---:|
| `local_auth` | `C` | `254` | `0` |
| `school_nam` | `C` | `254` | `0` |
| `la_s_code` | `C` | `254` | `0` |
| `seed_code` | `N` | `19` | `0` |
| `uprn` | `N` | `33` | `15` |
| `address` | `C` | `254` | `0` |
| `type` | `C` | `254` | `0` |
| `level` | `C` | `254` | `0` |
| `email` | `C` | `254` | `0` |
| `phone` | `C` | `254` | `0` |
| `website` | `C` | `254` | `0` |
| `sh_date_up` | `C` | `254` | `0` |
| `sh_src` | `C` | `254` | `0` |
| `sh_src_id` | `N` | `19` | `0` |

## Candidate matching fields

- `local_auth`
- `school_nam`
- `la_s_code`
- `seed_code`

## Sample records

Wrote first `30` records to:

```text
outputs/scotland-secondary-non-denom-schema/sample_records.csv
```

## Candidate field distinct-value summary

Wrote summary to:

```text
outputs/scotland-secondary-non-denom-schema/candidate_field_distinct_summary.csv
```