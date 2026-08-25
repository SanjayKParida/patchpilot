class RepositoryRankingService:
    """
    Scores candidate files by how likely they are to be directly relevant
    to a reported issue.

    Three channels observe whether a file is about a concept:

        evidence   how the concept appears in the code
                   (declaration, call, mention) — highest precision,
                   supplied by the language pack

        content    that the concept appears on a line, and roughly
                   what kind of line it was

        path       that the file is NAMED for the concept — a prior
                   about the file, not an observation of its code

    They are NOT independent. All three read the same underlying fact,
    so adding them together counts one fact three times. A generated
    config file named `firebase_options.dart` that says "Firebase" on
    fourteen lines used to collect a path award, a large content sum
    AND an evidence score for a single concept, and so outranked files
    that matched five of the issue's six concepts.

    Instead each channel produces a CONFIDENCE in [0, 1] that the file
    is about the concept, and the channels are combined as independent
    partial observations:

        combined = 1 - Π (1 - reliability_c × confidence_c)

    Corroboration still helps, but with diminishing returns, and the
    per-signal result is bounded. A file therefore cannot climb the
    ranking by shouting one concept loudly; it climbs by matching more
    of what the issue is actually about.

    This also gives "content is a fallback for what evidence cannot
    see" for free: where evidence is confident the residual term is
    small, so content adds little; where there is no language pack and
    evidence is silent, content carries the file on its own.

    Structural evidence stays a separate additive component. It is
    genuinely different information — graph topology rather than
    vocabulary — and it remains supporting evidence only.

    This service is deliberately language-agnostic.

    It never inspects Dart / Python / TypeScript specific evidence
    type names. Evidence records only need to carry:

        {
            "file": {...},
            "evidence_type": "<opaque string>",
            "concept": "<signal term>",
            "strength": 0.0 - 1.0
        }

    The language pack decides what an evidence type means and how
    strong it is. Ranking only decides how strength becomes score.
    """

    # ---------------------------------------------------------
    # Signal weighting
    # ---------------------------------------------------------
    #
    # How diagnostic is this KIND of concept for locating a defect?
    #
    #   behavior      names the SYMPTOM — "loading", "crash",
    #                 "duplicate", "timeout". The most direct pointer
    #                 a bug report contains at the broken behaviour.
    #
    #   architecture  names the LAYER — "repository", "bloc",
    #                 "controller". Narrows to a region of the code.
    #
    #   technology    names the STACK — "firebase", "postgres". In an
    #                 application built on that stack it appears
    #                 everywhere, so it identifies the project more
    #                 than the defect.
    #
    #   domain        names the ENTITY — "car", "user". In a
    #                 single-domain application it is close to
    #                 universal.
    #
    # The bottom two are deliberately low for the same reason: a term
    # that describes the whole repository cannot discriminate within
    # it. A generated `firebase_options.dart` matching one technology
    # signal loudly must not outrank a file matching the symptom.
    #
    # An inverse-document-frequency term was measured as an
    # alternative to this prior — see CONTEXT.md. It scored worse and
    # double-counted with these weights, so the prior stands alone.
    # ---------------------------------------------------------

    SIGNAL_WEIGHTS = {
        "behavior": 4,
        "architecture": 3,
        "technology": 2,
        "domain": 1,
    }

    # ---------------------------------------------------------
    # Channel reliability
    # ---------------------------------------------------------
    #
    # How much a fully-confident channel is trusted on its own.
    #
    # evidence  1.00  the language pack looked at the code and knows
    #                 whether the concept was declared or merely
    #                 mentioned
    #
    # path      0.45  the file is named for the concept. A real hint
    #                 about what the file is FOR, though trivially
    #                 satisfied by config and generated files
    #
    # content   0.30  the concept appears on a line somewhere. The
    #                 weakest of the three: blind to whether the file
    #                 owns the concept or merely references it, and
    #                 systematically over-confident on wiring files
    #                 that name everything they connect
    #
    # Content sits lowest because, now that a language pack reports
    # evidence, content's unique job is only what evidence cannot
    # see: files in languages with no pack, and mentions inside
    # strings or comments that the analyzer skips.
    #
    # The metric is flat across content in [0.25, 0.35] on the one
    # case measured so far, so treat this as a plateau rather than a
    # tuned optimum, and re-measure when a second case exists.
    # ---------------------------------------------------------

    CHANNEL_RELIABILITY = {
        "evidence": 1.0,
        "path": 0.45,
        "content": 0.30,
    }

    # ---------------------------------------------------------
    # Content channel
    # ---------------------------------------------------------

    MATCH_WEIGHTS = {
        "code": 5.0,
        "import": 1.0,
        "comment": 0.1,
    }

    # Match weight at which the content channel is half confident.
    # One `code` line already reaches 0.5.
    CONTENT_SATURATION = 5.0

    # ---------------------------------------------------------
    # Evidence channel
    # ---------------------------------------------------------
    #
    # Evidence records carry a strength from the language pack:
    #
    #   class            1.0
    #   function         0.9
    #   property_access  0.7
    #   annotation       0.7
    #   identifier       0.2
    #
    # Quantity must not beat quality, so repeated occurrences of the
    # SAME evidence type saturate towards that type's own strength:
    #
    #   contribution = strength × count / (count + SATURATION)
    #
    # With SATURATION = 0.5 a single occurrence is worth 0.667 of the
    # type's strength and many occurrences approach, but never reach,
    # the strength itself. Fifty identifier mentions therefore stay
    # below one class declaration.
    #
    # Distinct evidence types still stack, so a file that declares a
    # class AND uses it repeatedly outranks one that only names it.
    # ---------------------------------------------------------

    EVIDENCE_COUNT_SATURATION = 0.5

    # ---------------------------------------------------------
    # Depth versus breadth
    # ---------------------------------------------------------
    #
    # Raising combined confidence to a power before weighting makes
    # partial confidence across many concepts worth much less than
    # high confidence on a few.
    #
    # A dependency-injection container references every concept the
    # application wires together and owns none of them. Linearly it
    # collects five mediocre observations and outranks the file that
    # actually implements the behaviour. The exponent expresses the
    # distinction ranking cares about: is this file ABOUT the
    # concept, or does it merely mention it?
    #
    # 1.0 restores purely linear behaviour.
    # ---------------------------------------------------------

    CONFIDENCE_EXPONENT = 1.5

    # Raw evidence total that counts as full confidence. A class
    # declaration alone lands near 0.55; a declaration plus real usage
    # reaches 1.0.
    EVIDENCE_FULL_CONFIDENCE = 1.2

    DEFAULT_EVIDENCE_STRENGTH = 0.2

    # ---------------------------------------------------------
    # Structural relationship weights
    # ---------------------------------------------------------
    #
    # Relative ordering:
    #
    #   extends    an explicit type contract that also inherits
    #              behaviour, so a defect in the parent reaches
    #              the child directly
    #
    #   implements an explicit type contract without inherited
    #              behaviour
    #
    #   mixes_in   injected behaviour, still explicit but usually
    #              cross-cutting rather than the primary concern
    #
    #   imports    the weakest and by far the most common edge;
    #              almost every file imports something
    #
    # These must all stay well below direct evidence. They are
    # further reduced by STRUCTURAL_DAMPENING below.
    # ---------------------------------------------------------

    STRUCTURAL_WEIGHTS = {
        "extends": 1.0,
        "implements": 1.0,
        "mixes_in": 0.75,
        "imports": 0.5,
    }

    STRUCTURAL_DISTANCE_DECAY = 0.5

    # Direct scores are bounded per signal, so structural evidence
    # must be scaled to stay subordinate to them. At 0.10 a strong
    # close edge is worth roughly a quarter of a strong direct
    # observation, and structural stays under ~30% of any file's
    # total on the measured case.
    #
    # This was 0.25 while direct scores were unbounded sums; the two
    # numbers only mean anything relative to each other, so they must
    # be re-checked together whenever either scale changes.
    STRUCTURAL_DAMPENING = 0.10

    # Hard backstop: structural score a file may carry relative to
    # its own direct score. Connectivity must not manufacture
    # relevance. Dampening should keep this from binding in normal
    # cases; if it starts binding often, the dampening is wrong.
    STRUCTURAL_CAP_RATIO = 0.5

    # =========================================================
    # CHANNEL CONFIDENCES
    # =========================================================

    def path_confidence(self, matched):
        """
        A path either names the concept or it does not.
        """

        return 1.0 if matched else 0.0

    def content_confidence(self, match_weights):
        """
        Confidence from content search hits on one file.

        Saturating, so a file cannot climb indefinitely by repeating
        the same word.
        """

        total = sum(match_weights)

        if total <= 0:
            return 0.0

        return total / (total + self.CONTENT_SATURATION)

    def evidence_confidence(self, by_type):
        """
        Confidence from language-pack evidence on one file.

        `by_type` maps an opaque evidence type to
        {"strength": float, "count": int}.
        """

        raw = 0.0

        for entry in by_type.values():

            count = entry["count"]

            occurrence_factor = (
                count
                / (count + self.EVIDENCE_COUNT_SATURATION)
            )

            raw += entry["strength"] * occurrence_factor

        if raw <= 0:
            return 0.0

        return min(
            1.0,
            raw / self.EVIDENCE_FULL_CONFIDENCE,
        )

    def combine_confidences(self, confidences):
        """
        Combine per-channel confidences into one direct confidence.

        Independent-observation form:

            1 - Π (1 - reliability × confidence)

        Two channels agreeing beats one channel alone, but the second
        channel only claims a share of what the first left uncertain.
        That is what stops the same lexical fact being counted once
        per channel.
        """

        residual = 1.0

        for channel, confidence in confidences.items():

            if confidence <= 0:
                continue

            reliability = self.CHANNEL_RELIABILITY.get(
                channel,
                0.0,
            )

            residual *= (
                1.0 - reliability * confidence
            )

        return 1.0 - residual

    def rank(
        self,
        signal,
        path_results,
        content_results,
        structural_results=None,
        direct_evidence=None
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

        direct_evidence:
            Optional language-pack evidence records.

            Expected format:

            {
                "file": file,
                "evidence_type": "class",
                "concept": "firebase",
                "strength": 1.0
            }

            Records whose concept does not match this signal are
            ignored, so the caller may pass the full evidence set
            once per signal without pre-filtering it.

        Returns
        -------
        dict
            {
                sha: {
                    "path": ...,
                    "direct_score": ...,
                    "structural_score": ...,
                    "signals_matched": ...,
                    "path_confidence": ...,
                    "content_confidence": ...,
                    "evidence_confidence": ...
                }
            }

            The three confidences are diagnostics. They explain the
            direct score; they do not sum to it.
        """

        scores = {}

        structural_results = structural_results or []
        direct_evidence = direct_evidence or []

        signal_type = signal["type"]
        signal_term = signal["term"]

        signal_weight = self.SIGNAL_WEIGHTS.get(
            signal_type,
            1
        )

        # =====================================================
        # COLLECT PER-CHANNEL OBSERVATIONS
        # =====================================================
        #
        # Each channel is gathered per file first. Nothing is scored
        # until every channel has reported, because the combination
        # depends on what the other channels found.
        # =====================================================

        observations = {}

        def observe(file):
            sha = file["sha"]

            entry = observations.get(sha)

            if entry is None:
                entry = {
                    "file": file,
                    "path_matched": False,
                    "match_weights": [],
                    "evidence_by_type": {},
                }
                observations[sha] = entry

            return entry

        # -----------------------------------------------------
        # Path
        # -----------------------------------------------------

        for file in path_results:
            observe(file)["path_matched"] = True

        # -----------------------------------------------------
        # Content
        # -----------------------------------------------------

        for result in content_results:

            observe(result["file"])["match_weights"].append(
                self.MATCH_WEIGHTS.get(
                    result["match_type"],
                    0,
                )
            )

        # -----------------------------------------------------
        # Evidence
        #
        # rank() scores one signal at a time, so records for other
        # concepts are skipped here rather than by the caller.
        # -----------------------------------------------------

        signal_concept = str(signal_term).strip().lower()

        for record in direct_evidence:

            file = record.get("file")

            if not file or file.get("sha") is None:
                continue

            concept = str(
                record.get("concept", "")
            ).strip().lower()

            if concept != signal_concept:
                continue

            by_type = observe(file)["evidence_by_type"]

            evidence_type = record.get(
                "evidence_type",
                "unknown",
            )

            strength = record.get(
                "strength",
                self.DEFAULT_EVIDENCE_STRENGTH,
            )

            entry = by_type.setdefault(
                evidence_type,
                {"strength": 0, "count": 0},
            )

            entry["count"] += 1

            # A language pack may emit varying strengths for one
            # evidence type. Trust the strongest.
            if strength > entry["strength"]:
                entry["strength"] = strength

        # =====================================================
        # DIRECT CONFIDENCE
        # =====================================================
        #
        # Confidences are resolved for every file before anything is
        # scored, because how much this signal is WORTH depends on
        # how many files it reached.
        # =====================================================

        observed = []

        for sha, entry in observations.items():

            confidences = {
                "evidence": self.evidence_confidence(
                    entry["evidence_by_type"]
                ),
                "content": self.content_confidence(
                    entry["match_weights"]
                ),
                "path": self.path_confidence(
                    entry["path_matched"]
                ),
            }

            combined = self.combine_confidences(confidences)

            if combined <= 0:
                continue

            observed.append(
                (sha, entry["file"], confidences, combined)
            )

        # =====================================================
        # DIRECT SCORING
        # =====================================================

        for sha, file, confidences, combined in observed:

            direct_score = (
                combined ** self.CONFIDENCE_EXPONENT
                * signal_weight
            )

            score = self._ensure_score(
                scores,
                sha,
                file["path"],
            )

            score["direct_score"] += direct_score
            score["signals_matched"] += 1

            for channel, confidence in confidences.items():
                score[f"{channel}_confidence"] += confidence

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

            self._ensure_score(
                scores,
                sha,
                file["path"]
            )

            scores[sha]["structural_score"] += (
                structural_score
            )

        return scores

    # =========================================================
    # Score bookkeeping
    # =========================================================

    @staticmethod
    def _ensure_score(scores, sha, path):
        """
        Return the score entry for a file, creating it if needed.

        Every scoring stage may be the first one to see a file, so
        each component starts at zero.
        """

        if sha not in scores:

            scores[sha] = {
                "path": path,
                "direct_score": 0,
                "structural_score": 0,
                "signals_matched": 0,
                "path_confidence": 0,
                "content_confidence": 0,
                "evidence_confidence": 0,
            }

        return scores[sha]

    # =========================================================
    # Aggregate
    # =========================================================

    def aggregate(self, rankings):
        """
        Combine rankings from all issue signals.

        Each signal is ranked independently first, then the direct
        scores are summed. Summing across signals is deliberate: it
        is what rewards a file for matching more of what the issue is
        about. Summing across CHANNELS within one signal is what
        rank() avoids, because those are three views of one fact.
        """

        final_scores = {}

        # =====================================================
        # Combine scores from every signal
        # =====================================================

        accumulated = (
            "direct_score",
            "structural_score",
            "signals_matched",
            "path_confidence",
            "content_confidence",
            "evidence_confidence",
        )

        for ranking in rankings:

            for sha, score in ranking.items():

                entry = self._ensure_score(
                    final_scores,
                    sha,
                    score["path"],
                )

                for key in accumulated:
                    entry[key] += score.get(key, 0)

        # =====================================================
        # Calculate final scores
        # =====================================================

        for sha, score in final_scores.items():

            # -------------------------------------------------
            # Structural safeguard
            # -------------------------------------------------
            #
            # Structural evidence supports direct evidence; it does
            # not replace it. A file with real direct evidence may
            # be lifted by its connections, but connectivity alone
            # must not manufacture relevance.
            # -------------------------------------------------

            direct_score = score["direct_score"]

            if direct_score > 0:

                structural_cap = (
                    direct_score
                    * self.STRUCTURAL_CAP_RATIO
                )

                if score["structural_score"] > structural_cap:
                    score["structural_score"] = structural_cap

            score["total_score"] = (
                direct_score
                + score["structural_score"]
            )

        return final_scores
