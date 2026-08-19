class RepositoryRankingService:
    """
    Scores candidate files by how likely they are to be directly relevant
    to a reported issue.

    Evidence priority:

        direct content match
            >
        path match
            >
        structural relationship
            >
        distant structural relationship

    Structural evidence is supporting evidence. It should not dominate
    direct evidence simply because a file is highly connected in the
    repository graph.
    """

    SIGNAL_WEIGHTS = {
        "technology": 3,
        "behavior": 3,
        "architecture": 2,
        "domain": 1,
    }

    MATCH_WEIGHTS = {
        "code": 5.0,
        "import": 1.0,
        "comment": 0.1,
    }

    STRUCTURAL_WEIGHTS = {
        "implements": 1.0,
        "imports": 0.5,
    }

    STRUCTURAL_DISTANCE_DECAY = 0.5
    STRUCTURAL_DAMPENING = 0.25

    PATH_WEIGHT = 1.5

    def rank(
        self,
        signal,
        path_results,
        content_results,
        structural_results=None
    ):
        """
        Rank files for a single issue signal.

        Parameters
        ----------
        signal:
            {
                "term": "...",
                "type": "technology|behavior|architecture|domain"
            }

        path_results:
            Files whose path matched the signal.

        content_results:
            Content search results.

        structural_results:
            Optional structural relationships.

            Expected format:

            {
                "file": file,
                "relationship": "imports",
                "distance": 1
            }

        Returns
        -------
        dict
            {
                sha: {
                    "path": ...,
                    "path_score": ...,
                    "content_score": ...,
                    "structural_score": ...
                }
            }
        """

        scores = {}

        structural_results = structural_results or []

        signal_type = signal["type"]
        signal_term = signal["term"]

        signal_weight = self.SIGNAL_WEIGHTS.get(
            signal_type,
            1
        )

        print(
            f"\n[RANKING] signal={signal_term} "
            f"type={signal_type} "
            f"weight={signal_weight}"
        )

        # =====================================================
        # PATH SCORING
        # =====================================================

        for file in path_results:

            sha = file["sha"]

            if sha not in scores:

                scores[sha] = {
                    "path": file["path"],
                    "path_score": 0,
                    "content_score": 0,
                    "structural_score": 0
                }

            path_score = (
                signal_weight *
                self.PATH_WEIGHT
            )

            scores[sha]["path_score"] += path_score

            print(
                f"  [PATH] {file['path']} "
                f"contribution={path_score}"
            )

        # =====================================================
        # CONTENT SCORING
        # =====================================================

        content_matches = {}

        for result in content_results:

            file = result["file"]
            sha = file["sha"]

            if sha not in content_matches:

                content_matches[sha] = {
                    "file": file,
                    "weights": []
                }

            match_weight = self.MATCH_WEIGHTS.get(
                result["match_type"],
                0
            )

            content_matches[sha]["weights"].append(
                match_weight
            )

        # -----------------------------------------------------
        # Calculate content score for each file
        # -----------------------------------------------------

        for sha, data in content_matches.items():

            file = data["file"]
            weights = data["weights"]

            total_match_weight = sum(weights)

            print(
                f"  [CONTENT] {file['path']} "
                f"matches={len(weights)} "
                f"weights={weights} "
                f"total_match_weight={total_match_weight}"
            )

            if total_match_weight > 0:

                # -------------------------------------------------
                # Diminishing returns.
                #
                # Example:
                #
                # one strong code match should matter a lot.
                #
                # Many tiny import matches should not allow a file
                # to grow infinitely in score.
                # -------------------------------------------------

                match_score = (
                    total_match_weight /
                    (total_match_weight + 5)
                )

            else:

                match_score = 0

            signal_contribution = (
                match_score *
                signal_weight
            )

            print(
                f"  [CONTENT] {file['path']} "
                f"match_score={match_score:.2f} "
                f"signal_contribution="
                f"{signal_contribution:.2f}"
            )

            if sha not in scores:

                scores[sha] = {
                    "path": file["path"],
                    "path_score": 0,
                    "content_score": 0,
                    "structural_score": 0
                }

            scores[sha]["content_score"] += (
                signal_contribution
            )

        # =====================================================
        # STRUCTURAL SCORING
        # =====================================================
        #
        # Important:
        #
        # We DO NOT simply sum every structural edge.
        #
        # Otherwise a shared model such as:
        #
        #     car.dart
        #
        # could receive a huge score simply because ten files
        # import it.
        #
        # Instead:
        #
        #   1. Group structural evidence by file.
        #
        #   2. For each relationship type, keep only the closest
        #      relationship.
        #
        #   3. Different relationship types can still contribute.
        #
        # Example:
        #
        #     imports    distance 1
        #     imports    distance 2
        #     imports    distance 3
        #
        # becomes:
        #
        #     imports    distance 1
        #
        # But:
        #
        #     imports    distance 1
        #     implements distance 2
        #
        # can both contribute.
        # =====================================================

        structural_best = {}

        for result in structural_results:

            file = result["file"]
            sha = file["sha"]

            relationship = result["relationship"]
            distance = result["distance"]

            relationship_weight = self.STRUCTURAL_WEIGHTS.get(
                relationship,
                0
            )

            if relationship_weight == 0:
                continue

            # -------------------------------------------------
            # Distance decay
            # -------------------------------------------------

            distance_factor = (
                self.STRUCTURAL_DISTANCE_DECAY
                ** (distance - 1)
            )

            entry = structural_best.setdefault(
                sha,
                {
                    "file": file,
                    "relationships": {}
                }
            )

            best_so_far = entry["relationships"].get(
                relationship,
                0
            )

            # Keep only the strongest/closest relationship of
            # each type for this file.
            if distance_factor > best_so_far:

                entry["relationships"][
                    relationship
                ] = distance_factor

        # -----------------------------------------------------
        # Calculate structural score
        # -----------------------------------------------------

        for sha, data in structural_best.items():

            file = data["file"]

            raw_contribution = 0

            for (
                relationship,
                distance_factor
            ) in data["relationships"].items():

                relationship_weight = (
                    self.STRUCTURAL_WEIGHTS[
                        relationship
                    ]
                )

                edge_contribution = (
                    relationship_weight *
                    distance_factor
                )

                raw_contribution += (
                    edge_contribution
                )

                print(
                    f"  [STRUCTURAL] {file['path']} "
                    f"relationship={relationship} "
                    f"best_distance_factor="
                    f"{distance_factor:.3f} "
                    f"edge_contribution="
                    f"{edge_contribution:.2f}"
                )

            # -------------------------------------------------
            # Apply:
            #
            # relationship score
            # × signal importance
            # × structural dampening
            # -------------------------------------------------

            structural_score = (
                raw_contribution *
                signal_weight *
                self.STRUCTURAL_DAMPENING
            )

            if sha not in scores:

                scores[sha] = {
                    "path": file["path"],
                    "path_score": 0,
                    "content_score": 0,
                    "structural_score": 0
                }

            scores[sha]["structural_score"] += (
                structural_score
            )

            print(
                f"  [STRUCTURAL] {file['path']} "
                f"total_contribution="
                f"{structural_score:.2f}"
            )

        return scores

    # =========================================================
    # Aggregate
    # =========================================================

    def aggregate(self, rankings):
        """
        Combine rankings from all issue signals.

        Example signals:

            firebase
            firestore
            loading
            car
            repository
            bloc

        Each signal is ranked independently first.

        Then all scores are combined.
        """

        final_scores = {}

        # =====================================================
        # Combine scores from every signal
        # =====================================================

        for ranking in rankings:

            for sha, score in ranking.items():

                if sha not in final_scores:

                    final_scores[sha] = {
                        "path": score["path"],
                        "path_score": 0,
                        "content_score": 0,
                        "structural_score": 0
                    }

                final_scores[sha]["path_score"] += (
                    score["path_score"]
                )

                final_scores[sha]["content_score"] += (
                    score["content_score"]
                )

                final_scores[sha]["structural_score"] += (
                    score.get(
                        "structural_score",
                        0
                    )
                )

        # =====================================================
        # Calculate final scores
        # =====================================================

        for sha, score in final_scores.items():

            direct_score = (
                score["path_score"] +
                score["content_score"]
            )

            # -------------------------------------------------
            # Structural safeguard
            # -------------------------------------------------
            #
            # If a file has direct evidence, structural evidence
            # should not be allowed to completely overwhelm it.
            #
            # Structural score can still contribute strongly,
            # but it is capped relative to that file's own
            # direct evidence.
            #
            # Example:
            #
            # direct = 10
            #
            # maximum structural = 15
            #
            # This prevents structural connectivity from
            # completely dominating the ranking.
            # -------------------------------------------------

            if direct_score > 0:

                structural_cap = (
                    direct_score *
                    1.5
                )

                if (
                    score["structural_score"]
                    > structural_cap
                ):

                    score["structural_score"] = (
                        structural_cap
                    )

            # -------------------------------------------------
            # Final score
            # -------------------------------------------------

            score["total_score"] = (
                score["path_score"]
                +
                score["content_score"]
                +
                score["structural_score"]
            )

        return final_scores