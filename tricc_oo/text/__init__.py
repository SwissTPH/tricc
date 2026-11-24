"""Display text as ProseMirror documents (``feature/20261120-prosemirror-display-text.md``).

- :mod:`tricc_oo.text.schema`: the schema shared with the frontend (TipTap names).
- :mod:`tricc_oo.text.parse`: draw.io HTML, Markdown, ProseMirror JSON and the old message
  tree in, as a document in canonical form.
- :mod:`tricc_oo.text.render`: plain text, Markdown, XHTML, references, dynamic text out.
- :mod:`tricc_oo.text.model`: ``TriccText``, a document plus what its ``${name}`` stand for.
"""

from tricc_oo.text.parse import (  # noqa: F401
    TextSchemaError,
    from_html,
    from_json,
    from_markdown,
    from_message_json,
    from_plain,
    from_text,
    normalize,
    simplify,
)
from tricc_oo.text.render import (  # noqa: F401
    references,
    to_concatenate,
    to_markdown,
    to_plain,
    to_xhtml,
)
