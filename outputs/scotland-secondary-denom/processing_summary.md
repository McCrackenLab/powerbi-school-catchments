# Scotland Secondary Denominational Catchment Processing Summary

## Inputs

- Shapefile: `incoming/scotland-secondary-denom/denom_pub_schlsd.shp`
- Schools CSV: `inputs/scottish_secondary_schools_for_mapping.csv`
- Lookup CSV: `outputs/scotland-secondary-non-denom/school_reference_layer_lookup_plus_scotland_sn.csv`

## Outputs

- Split GeoJSON folder: `scotland-secondary-denom-catchments`
- Updated lookup: `outputs/scotland-secondary-denom/school_reference_layer_lookup_plus_scotland_sn_sd.csv`
- Match review: `outputs/scotland-secondary-denom/scotland_sd_catchment_match_review.csv`
- GeoJSON index: `outputs/scotland-secondary-denom/scotland_sd_catchment_geojson_index.csv`

## Counts

- Catchment records processed: `63`
- GeoJSON files created: `63`
- Matched catchments: `54`
- Unmatched catchments: `9`
- Seed-code matches: `53`
- School name + LA matches: `1`
- School name only matches: `0`
- Lookup rows with real catchment URL after update: `346`

## Notes

The source shapefile is assumed to be EPSG:27700 British National Grid and is transformed to EPSG:4326 for GeoJSON output.

This denominational run starts from the Scotland SN lookup and adds matched secondary denominational catchment URLs.
