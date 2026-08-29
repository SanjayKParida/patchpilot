from app.code_intelligence.types import Span
from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer
from app.utils.dart.dart_symbol_locator import DartSymbolLocator


class DartSpanLocator:
    """
    Finds where a Dart declaration ends.

    DartSymbolLocator answers where a declaration STARTS. Slicing needs
    its extent: a patch generator handed the first line of a method and
    nothing else cannot change it.

    Brace matching over masked source, which is heuristic — so the rule
    throughout is that an uncertain answer is None. A wrong span
    silently truncates the code a patch is reasoned about, and the
    caller already knows how to fall back to a fixed window. Declining
    costs context; guessing costs correctness.

    Three things make naive brace counting wrong in Dart, and each is
    handled explicitly below:

        1. Braces inside comments and string literals. Solved by
           masking before scanning.

        2. Named and optional parameters are braces:

               CarBloc({required this.getCars}) : super(...) {

           Counting them as a body closes the declaration at the end
           of its own parameter list. Braces are therefore ignored
           while inside parentheses.

        3. Calls that look like declarations. `const Icon(...)` in a
           widget tree matches the shared `Type name(` pattern. A
           parameter list followed by a comma or a closing bracket is
           an argument, not a declaration, and is refused.

        4. Bodies that are expressions, not blocks:

               Future<void> load() => repository.fetch();

           These have no brace at all and end at the first semicolon.
           The same rule covers abstract methods and field
           declarations, which also end at a semicolon.
    """

    # A declaration longer than this is either a very large class or a
    # failure to find the closing brace. Either way, stop: an unbounded
    # scan over a malformed file helps nobody.
    MAX_SPAN_LINES = 400

    def __init__(self, structure_analyzer=None):
        self.structure = structure_analyzer or DartStructureAnalyzer()

    # =========================================================
    # PUBLIC API
    # =========================================================

    def enclosing_span(self, path, line, content):
        """
        The innermost declaration whose extent contains `line`.

        Innermost, not outermost: a line inside a method should yield
        the method, not the 300-line class around it. The caller merges
        and pads slices, so a tight span is the more useful primitive.

        Returns None when `line` is outside the file, sits in no
        declaration, or the declaration cannot be closed confidently.
        """

        if not content or line is None or line < 1:
            return None

        code = self.structure.mask_source(content)
        lines = code.splitlines()

        if line > len(lines):
            return None

        best = None

        for start, kind, symbol in self.declarations(lines):

            # Declarations are in line order, so nothing after `line`
            # can begin a span that contains it.
            if start > line:
                break

            end = self.span_end(lines, start)

            if end is None or end < line:
                continue

            # Later start means more deeply nested.
            if best is None or start > best[0]:
                best = (start, end, kind, symbol)

        if best is None:
            return None

        return Span(
            path=path,
            start_line=best[0],
            end_line=best[1],
            kind=best[2],
            symbol=best[3],
        )

    # =========================================================
    # DECLARATIONS
    # =========================================================

    def declarations(self, lines):
        """
        Every declaration start in masked source, in line order.

        Reuses DartSymbolLocator's patterns so the pack keeps ONE
        definition of what a declaration looks like. A span that
        started somewhere the symbol locator does not consider a
        declaration would point at code no location ever names.
        """

        found = []

        for number, text in enumerate(lines, start=1):

            for kind, pattern in DartSymbolLocator.DECLARATION_PATTERNS:

                match = pattern.search(text)

                if not match:
                    continue

                found.append((number, kind, match.group("name")))
                break

        return found

    # =========================================================
    # EXTENT
    # =========================================================

    def span_end(self, lines, start):
        """
        Last line of the declaration beginning at `start`, or None.

        Expects masked source: braces inside comments and strings must
        already be gone.
        """

        depth = 0
        parens = 0
        in_body = False

        # Set the moment a parameter list closes, cleared by the next
        # non-space character. See the ',' / ')' check below.
        after_params = False

        limit = min(
            len(lines),
            start - 1 + self.MAX_SPAN_LINES,
        )

        for index in range(start - 1, limit):

            for character in lines[index]:

                if character == "(":
                    parens += 1
                    after_params = False
                    continue

                if character == ")":
                    # Never let a stray ')' drive the count negative;
                    # it would make later braces look top-level.
                    parens = max(0, parens - 1)
                    after_params = parens == 0
                    continue

                # Only the declaration's OWN signature is checked.
                # Once a body is open, every `foo(a), ` in a list
                # literal would otherwise look like a call-shaped
                # false positive and abandon the whole declaration.
                if after_params and not in_body:

                    if character.isspace():
                        continue

                    # A real declaration continues into a body, an
                    # initializer list, a semicolon or `async`. A
                    # comma or a closing bracket means this was a CALL
                    # sitting in an argument list — `const Icon(...)`,
                    # in a widget tree — which the shared declaration
                    # patterns cannot distinguish from a declaration.
                    #
                    # Refusing here is what stops a false-positive
                    # declaration becoming a code slice.
                    if character in ",)]}":
                        return None

                    after_params = False

                # Parameter braces are not a body. Skip anything
                # nested inside parentheses entirely.
                if parens > 0:
                    continue

                if character == "{":
                    depth += 1
                    in_body = True
                    continue

                if character == "}":
                    depth -= 1

                    if depth == 0 and in_body:
                        return index + 1

                    if depth < 0:
                        # Closed a brace this declaration never
                        # opened: the start line was not a real
                        # declaration, or the file is malformed.
                        return None

                    continue

                if character == ";" and not in_body and depth == 0:
                    # No block body: an expression body, an abstract
                    # method, a typedef or a field.
                    return index + 1

        return None
