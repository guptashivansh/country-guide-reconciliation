class EmploymentRuleAggregator:
    def aggregate(self, chunk_results):
        best_by_section = {}

        for chunk_result in chunk_results:
            chunk_index = chunk_result["chunk_index"]
            chunk_count = chunk_result["chunk_count"]
            source_url = chunk_result["source_url"]

            for rule in chunk_result["rules"]:
                enriched_rule = {
                    **rule,
                    "source_url": source_url,
                    "source_chunk_index": chunk_index,
                    "source_chunk_count": chunk_count,
                }
                current = best_by_section.get(rule["section"])
                if current is None or rule["confidence"] > current["confidence"]:
                    best_by_section[rule["section"]] = enriched_rule

        return [
            best_by_section[section]
            for section in sorted(best_by_section.keys())
        ]
