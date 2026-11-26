# Filter Query Latency

![Latency trends](filter_latency_trends.png)

| Scale | Rows | Query | Query Type | P95 (ms) | Max (ms) |
|---:|---:|---|---|---:|---:|
| 25% | 59,897 | summary_statistics | simple | 3.480 | 3.740 |
| 25% | 59,897 | summary_statistics | compound | 3.494 | 3.721 |
| 25% | 59,897 | temporal_trends | simple | 3.553 | 3.936 |
| 25% | 59,897 | temporal_trends | compound | 4.097 | 4.495 |
| 25% | 59,897 | severity_distribution | simple | 3.692 | 3.850 |
| 25% | 59,897 | severity_distribution | compound | 3.910 | 13.619 |
| 25% | 59,897 | collision_type_distribution | simple | 3.713 | 4.031 |
| 25% | 59,897 | collision_type_distribution | compound | 4.604 | 4.790 |
| 25% | 59,897 | geographic_hotspots | simple | 4.148 | 4.587 |
| 25% | 59,897 | geographic_hotspots | compound | 4.396 | 4.870 |
| 50% | 119,794 | summary_statistics | simple | 3.466 | 6.691 |
| 50% | 119,794 | summary_statistics | compound | 3.596 | 3.692 |
| 50% | 119,794 | temporal_trends | simple | 3.660 | 9.153 |
| 50% | 119,794 | temporal_trends | compound | 4.620 | 5.055 |
| 50% | 119,794 | severity_distribution | simple | 3.781 | 8.168 |
| 50% | 119,794 | severity_distribution | compound | 3.995 | 9.401 |
| 50% | 119,794 | collision_type_distribution | simple | 3.744 | 3.833 |
| 50% | 119,794 | collision_type_distribution | compound | 5.239 | 5.487 |
| 50% | 119,794 | geographic_hotspots | simple | 4.387 | 4.440 |
| 50% | 119,794 | geographic_hotspots | compound | 4.755 | 7.833 |
| 75% | 179,691 | summary_statistics | simple | 3.768 | 4.227 |
| 75% | 179,691 | summary_statistics | compound | 3.897 | 4.049 |
| 75% | 179,691 | temporal_trends | simple | 4.152 | 4.907 |
| 75% | 179,691 | temporal_trends | compound | 5.064 | 8.022 |
| 75% | 179,691 | severity_distribution | simple | 4.335 | 4.943 |
| 75% | 179,691 | severity_distribution | compound | 4.268 | 4.555 |
| 75% | 179,691 | collision_type_distribution | simple | 4.342 | 5.054 |
| 75% | 179,691 | collision_type_distribution | compound | 5.861 | 7.635 |
| 75% | 179,691 | geographic_hotspots | simple | 4.843 | 5.214 |
| 75% | 179,691 | geographic_hotspots | compound | 5.373 | 7.827 |
| 100% | 239,588 | summary_statistics | simple | 3.627 | 4.637 |
| 100% | 239,588 | summary_statistics | compound | 3.844 | 4.033 |
| 100% | 239,588 | temporal_trends | simple | 3.855 | 3.971 |
| 100% | 239,588 | temporal_trends | compound | 4.995 | 5.073 |
| 100% | 239,588 | severity_distribution | simple | 3.987 | 4.052 |
| 100% | 239,588 | severity_distribution | compound | 4.347 | 5.313 |
| 100% | 239,588 | collision_type_distribution | simple | 4.439 | 6.013 |
| 100% | 239,588 | collision_type_distribution | compound | 6.003 | 6.282 |
| 100% | 239,588 | geographic_hotspots | simple | 4.728 | 6.716 |
| 100% | 239,588 | geographic_hotspots | compound | 5.418 | 11.840 |
