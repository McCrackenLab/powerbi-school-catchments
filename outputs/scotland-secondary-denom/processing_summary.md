# Scotland Secondary Denominational Catchment Processing Summary

## Inputs

- Shapefile: `incoming/scotland-secondary-denom/denom_pub_schlsd.shp`
- Schools CSV: `inputs/scottish_secondary_schools_for_mapping.csv`
- Lookup CSV: `outputs/scotland-secondary-non-denom/school_reference_layer_lookup_plus_scotland_sn.csv`
- Manual overrides CSV: `inputs/scotland_sd_manual_catchment_overrides.csv`

## Outputs

- Row-level GeoJSON folder: `scotland-secondary-denom-catchments`
- Combined per-school GeoJSON folder: `scotland-secondary-denom-catchments/combined-by-school`
- Updated lookup: `outputs/scotland-secondary-denom/school_reference_layer_lookup_plus_scotland_sn_sd.csv`
- Match review: `outputs/scotland-secondary-denom/scotland_sd_catchment_match_review.csv`
- Row-level GeoJSON index: `outputs/scotland-secondary-denom/scotland_sd_catchment_geojson_index.csv`
- Combined per-school GeoJSON index: `outputs/scotland-secondary-denom/scotland_sd_combined_by_school_index.csv`

## Counts

- Catchment records processed: `63`
- Row-level GeoJSON files created: `63`
- Combined per-school GeoJSON files created: `54`
- Schools with multiple denominational catchment features: `8`
- Matched catchments: `63`
- Unmatched catchments: `0`
- Seed-code matches: `53`
- Manual override matches: `9`
- Manual override target not found: `0`
- Manual override multiple matches: `0`
- School name + LA matches: `1`
- School name only matches: `0`
- Lookup rows with real catchment URL after update: `350`

## Notes

The source shapefile is assumed to be EPSG:27700 British National Grid and is transformed to EPSG:4326 for GeoJSON output.

Manual overrides are applied before automatic seed-code and name matching.

For every matched school, the lookup now points to a combined per-school GeoJSON file. This avoids losing cross-authority or multi-part denominational catchment polygons when a school appears in more than one source catchment record.
