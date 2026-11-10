# Collision Data Quality Report

## Processing results

- Original rows: 239,588
- Cleaned rows: 239,588
- Original columns: 52
- Derived columns: 5
- DuckDB rows: 239,588
- Years: 2014–2023
- Total killed: 2,479
- Total injured: 181,254

## Important missing values

- `collision_time`: 1,267
- `distance`: 20,525
- `state_route`: 63,196
- `postmile`: 46,446
- `control_device`: 26,397
- `stwd_vehtype_at_fault`: 36,851
- `location_sandag`: 18,966
- `reservation_sandag`: 18,966

Missing values were retained. All 2023 records have null `distance`,
`location_sandag`, and `reservation_sandag`, as documented in the specification.

## Duplicate case ID

Case ID `6820212021` has 2 records. Both were retained.
No exact duplicate source rows were found.

## Normalized severity

- Property Damage Only: 106,687
- Injury (Complaint of Pain): 76,229
- Injury (Other Visible): 45,412
- Injury (Severe): 8,933
- Fatal: 2,327

Only `PDO` was normalized to `Property Damage Only`; the original severity field
was preserved.

## Validation

- Pre-ingestion test suite for this implementation: 12 passed
- Invalid dates: 0
- Invalid non-null times: 0
- Out-of-range coordinates: 0
- Injury total mismatches: 0
- Unexpected severity categories: 0
- Known distance outliers were preserved without modification.

## DuckDB schema

- `accident_year`: `INTEGER`
- `collision_date`: `DATE`
- `collision_time`: `TIME`
- `day_of_week`: `VARCHAR`
- `primary_rd`: `VARCHAR`
- `secondary_rd`: `VARCHAR`
- `distance`: `DOUBLE`
- `direction`: `VARCHAR`
- `intersection`: `VARCHAR`
- `weather_1`: `VARCHAR`
- `state_hwy_ind`: `VARCHAR`
- `state_route`: `INTEGER`
- `postmile`: `DOUBLE`
- `location_type`: `VARCHAR`
- `ramp_intersection`: `VARCHAR`
- `collision_severity`: `VARCHAR`
- `number_killed`: `INTEGER`
- `number_injured`: `INTEGER`
- `party_count`: `INTEGER`
- `pcf_viol_category`: `VARCHAR`
- `hit_and_run`: `VARCHAR`
- `type_of_collision`: `VARCHAR`
- `mviw`: `VARCHAR`
- `ped_action`: `VARCHAR`
- `road_surface`: `VARCHAR`
- `road_cond_1`: `VARCHAR`
- `lighting`: `VARCHAR`
- `control_device`: `VARCHAR`
- `chp_road_type`: `INTEGER`
- `pedestrian_accident`: `BOOLEAN`
- `bicycle_accident`: `BOOLEAN`
- `motorcycle_accident`: `BOOLEAN`
- `truck_accident`: `BOOLEAN`
- `alcohol_involved`: `BOOLEAN`
- `stwd_vehtype_at_fault`: `VARCHAR`
- `count_severe_inj`: `INTEGER`
- `count_visible_inj`: `INTEGER`
- `count_complaint_pain`: `INTEGER`
- `count_ped_killed`: `INTEGER`
- `count_ped_injured`: `INTEGER`
- `count_bicyclist_killed`: `INTEGER`
- `count_bicyclist_injured`: `INTEGER`
- `count_mc_killed`: `INTEGER`
- `count_mc_injured`: `INTEGER`
- `sandag_case_id`: `VARCHAR`
- `latitude_sandag`: `DOUBLE`
- `longitude_sandag`: `DOUBLE`
- `x`: `DOUBLE`
- `y`: `DOUBLE`
- `location_sandag`: `VARCHAR`
- `reservation_sandag`: `VARCHAR`
- `shape`: `VARCHAR`
- `severity_normalized`: `VARCHAR`
- `collision_year`: `INTEGER`
- `collision_month`: `INTEGER`
- `collision_weekday`: `VARCHAR`
- `collision_hour`: `INTEGER`
