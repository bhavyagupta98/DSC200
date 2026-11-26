# Filter Query Latency

![Latency trends](filter_latency_trends.png)

| Scale | Rows | Query | Query Type | P95 (ms) | Max (ms) |
|---:|---:|---|---|---:|---:|
| 25% | 59,897 | summary_statistics | simple | 3.375 | 3.656 |
| 25% | 59,897 | summary_statistics | compound | 3.423 | 3.491 |
| 25% | 59,897 | temporal_trends | simple | 3.484 | 6.302 |
| 25% | 59,897 | temporal_trends | compound | 4.078 | 10.755 |
| 25% | 59,897 | severity_distribution | simple | 3.625 | 3.705 |
| 25% | 59,897 | severity_distribution | compound | 3.802 | 3.968 |
| 25% | 59,897 | collision_type_distribution | simple | 3.631 | 10.425 |
| 25% | 59,897 | collision_type_distribution | compound | 4.417 | 6.367 |
| 25% | 59,897 | geographic_hotspots | simple | 4.058 | 8.690 |
| 25% | 59,897 | geographic_hotspots | compound | 4.253 | 4.352 |
| 50% | 119,794 | summary_statistics | simple | 3.490 | 3.789 |
| 50% | 119,794 | summary_statistics | compound | 3.591 | 3.670 |
| 50% | 119,794 | temporal_trends | simple | 3.640 | 3.680 |
| 50% | 119,794 | temporal_trends | compound | 4.640 | 4.890 |
| 50% | 119,794 | severity_distribution | simple | 3.799 | 3.868 |
| 50% | 119,794 | severity_distribution | compound | 4.039 | 4.093 |
| 50% | 119,794 | collision_type_distribution | simple | 3.787 | 4.021 |
| 50% | 119,794 | collision_type_distribution | compound | 5.268 | 5.364 |
| 50% | 119,794 | geographic_hotspots | simple | 4.422 | 4.512 |
| 50% | 119,794 | geographic_hotspots | compound | 4.764 | 4.925 |
| 75% | 179,691 | summary_statistics | simple | 3.556 | 3.657 |
| 75% | 179,691 | summary_statistics | compound | 3.739 | 3.808 |
| 75% | 179,691 | temporal_trends | simple | 3.753 | 3.798 |
| 75% | 179,691 | temporal_trends | compound | 4.861 | 4.966 |
| 75% | 179,691 | severity_distribution | simple | 3.897 | 3.989 |
| 75% | 179,691 | severity_distribution | compound | 4.179 | 4.234 |
| 75% | 179,691 | collision_type_distribution | simple | 3.952 | 4.025 |
| 75% | 179,691 | collision_type_distribution | compound | 5.568 | 5.961 |
| 75% | 179,691 | geographic_hotspots | simple | 4.594 | 4.758 |
| 75% | 179,691 | geographic_hotspots | compound | 5.088 | 5.158 |
| 100% | 239,588 | summary_statistics | simple | 3.664 | 3.742 |
| 100% | 239,588 | summary_statistics | compound | 3.797 | 3.822 |
| 100% | 239,588 | temporal_trends | simple | 3.848 | 4.034 |
| 100% | 239,588 | temporal_trends | compound | 5.024 | 5.120 |
| 100% | 239,588 | severity_distribution | simple | 4.025 | 4.114 |
| 100% | 239,588 | severity_distribution | compound | 4.300 | 4.336 |
| 100% | 239,588 | collision_type_distribution | simple | 4.324 | 4.371 |
| 100% | 239,588 | collision_type_distribution | compound | 5.903 | 6.084 |
| 100% | 239,588 | geographic_hotspots | simple | 4.725 | 4.909 |
| 100% | 239,588 | geographic_hotspots | compound | 5.202 | 5.711 |
