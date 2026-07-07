# Scotland Secondary Non-Denominational Catchment Processing Summary

## Inputs

- Shapefile: `incoming/scotland-secondary-non-denom/non_denom_pub_schlsn.shp`
- Schools CSV: `inputs/scottish_secondary_schools_for_mapping.csv`
- Lookup CSV: `inputs/school_reference_layer_lookup_with_fallback_and_fife_catchments.csv`
- Manual overrides CSV: `inputs/scotland_sn_manual_catchment_overrides.csv`

## Outputs

- Split GeoJSON folder: `scotland-secondary-non-denom-catchments`
- Updated lookup: `outputs/scotland-secondary-non-denom/school_reference_layer_lookup_plus_scotland_sn.csv`
- Match review: `outputs/scotland-secondary-non-denom/scotland_sn_catchment_match_review.csv`
- GeoJSON index: `outputs/scotland-secondary-non-denom/scotland_sn_catchment_geojson_index.csv`

## Counts

- Catchment records processed: `324`
- GeoJSON files created: `324`
- Matched catchments: `305`
- Unmatched catchments: `19`
- Seed-code matches: `278`
- Manual override matches: `23`
- Manual override target not found: `0`
- Manual override multiple matches: `0`
- School name + LA matches: `2`
- School name only matches: `2`
- Lookup rows with real catchment URL after update: `296`

## Notes

The source shapefile is assumed to be EPSG:27700 British National Grid and is transformed to EPSG:4326 for GeoJSON output.

Manual overrides are applied before automatic seed-code and name matching.
