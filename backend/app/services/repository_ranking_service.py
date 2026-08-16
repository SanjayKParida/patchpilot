import math

class RepositoryRankingService:
    SIGNAL_WEIGHTS = {
        "technology": 3,
        "behavior": 3,
        "architecture": 2,
        "domain": 1,
    }

    MATCH_WEIGHTS = {
        "import": 0.5,
        "comment": 0,
        "code": 3,
    }

    PATH_WEIGHT = 1

    def rank(self, signal, path_results, content_results):
        scores = {}

        signal_type = signal["type"]
        signal_weight = self.SIGNAL_WEIGHTS.get(signal_type, 1)

        for file in path_results:
            sha = file['sha']
            if sha not in scores:
                scores[sha] = {
                    "path": file["path"],
                    "path_score": 0,
                    "content_score": 0
                }
            scores[sha]["path_score"] += (signal_weight * self.PATH_WEIGHT)

        content_matches = {}
        for result in content_results:
            file = result["file"]
            sha = file["sha"]

            if sha not in content_matches:
                content_matches[sha] = {
                    "file": file,
                    "weights":[]
                }

            match_weight = self.MATCH_WEIGHTS.get(
                result["match_type"],
                0
            )

            content_matches[sha]["weights"].append(match_weight)
        

        for sha, data in content_matches.items():
            file = data["file"]
            weights = data["weights"]

            total_match_weight = sum(weights)

            if total_match_weight > 0:
                match_score = 1 + math.log(total_match_weight)
            else:
                match_score = 0

            if sha not in scores:
                scores[sha] = {
                    "path": file["path"],
                    "path_score": 0,
                    "content_score": 0
                }
            
            scores[sha]["content_score"] += (match_score * signal_weight)

        return scores

    def aggregate(self, rankings):
        final_scores = {}
        for ranking in rankings:
            for sha, score in ranking.items():
                if sha not in final_scores:
                    final_scores[sha] = {
                        "path": score["path"],
                        "path_score": 0,
                        "content_score": 0
                    }

                final_scores[sha]["path_score"] += score["path_score"]
                final_scores[sha]["content_score"] += score["content_score"]
        
        for sha, score in final_scores.items():
            score["total_score"] = (
                score["path_score"] +
                score["content_score"]
            )
        
        return final_scores