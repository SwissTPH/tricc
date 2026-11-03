"""XLSForm translations from the project CodeSystem designations.

With ``parameters.languages`` configured, every text column (``label``, ``hint``,
``help``, ``constraint_message``, ``required_message``) is written once per language
as ``<column>::<lang>``. The default-language column keeps the text the form was built
with; the others come from the designations of the row's concept (``display`` /
``hint`` / ``help``), else from the gettext catalogue (``models/lang.py``), else the
default-language text. Without ``parameters.languages`` the frames are left untouched.
"""

import logging

from tricc_oo.converters.datadictionnary import concept_text, find_concept, lookup_codesystems_code
from tricc_oo.converters.utils import remove_html_full
from tricc_oo.models.lang import SingletonLangClass

logger = logging.getLogger("default")

TRANSLATED_COLUMNS = ["label", "hint", "help", "constraint_message", "required_message"]
# column -> designation use, for a row printed from a node
NODE_TEXT_USES = {"label": "display", "hint": "hint", "help": "help"}
# the "more info" note shows the node help as its label
MORE_INFO_TEXT_USES = {"label": "help_body"}


def remember_row(strategy, key, node, uses=None):
    """Record which node printed a survey / choices row (key: ("survey", name) or
    ("choices", list_name, value)) so its texts can be translated at export."""
    rows = getattr(strategy, "translation_rows", None)
    if rows is not None and key not in rows:
        rows[key] = (node, uses or NODE_TEXT_USES)


def node_concept(project, node):
    """The CodeSystem concept of a node: its explicit concept link, else its name."""
    code_systems = getattr(project, "code_systems", None)
    if not code_systems or node is None:
        return None
    code = getattr(node, "concept_code", None)
    if code:
        return find_concept(code_systems, code, getattr(node, "concept_system", None))
    name = getattr(node, "name", None)
    return lookup_codesystems_code(code_systems, name) if isinstance(name, str) and name else None


def translations_active(project):
    languages = getattr(project, "languages", None)
    return isinstance(languages, list) and bool(languages)


def default_language_setting(project):
    """``settings.default_language``: the language code once columns are per language."""
    return project.lang_code if translations_active(project) else "English (en)"


def _gettext(text, lang):
    catalogues = SingletonLangClass().languages or {}
    if isinstance(text, str) and text.strip() and lang in catalogues:
        return catalogues[lang].gettext(text.strip())
    return text


def _designation(concept, use, lang, default_lang):
    if concept is None or use is None:
        return None
    if use == "help_body":
        from tricc_oo.serializers.xls_form import extract_help_title

        text = concept_text(concept, "help", lang, default_lang)
        return extract_help_title(text)[1] if text else None
    text = concept_text(concept, use, lang, default_lang)
    if text and use == "hint":
        text = remove_html_full(text)
    return text


def _translate_frame(project, df, key_of, rows):
    default = project.lang_code
    others = [lang for lang in project.languages if lang != default]
    columns = [c for c in TRANSLATED_COLUMNS if c in df.columns]
    if not columns or is_translated(df):
        return df
    out = df.copy()
    entries = [rows.get(key_of(row)) for _, row in out.iterrows()]
    concepts = [node_concept(project, e[0]) if e else None for e in entries]
    for column in columns:
        default_values = list(out[column])
        for lang in others:
            values = []
            for value, entry, concept in zip(default_values, entries, concepts):
                use = entry[1].get(column) if entry else None
                text = _designation(concept, use, lang, default)
                values.append(text if text else _gettext(value, lang))
            out[f"{column}::{lang}"] = values
        out = out.rename(columns={column: f"{column}::{default}"})
    # keep each language group where the plain column was
    order = []
    for column in df.columns:
        if column in columns:
            order.append(f"{column}::{default}")
            order += [f"{column}::{lang}" for lang in others]
        else:
            order.append(column)
    return out[order]


def translate_frames(strategy, project, df_survey, df_choice):
    """Return ``(df_survey, df_choice)`` with one text column per configured language."""
    if project is None or not translations_active(project):
        return df_survey, df_choice
    rows = getattr(strategy, "translation_rows", None) or {}
    if df_survey is not None and "name" in df_survey.columns:
        df_survey = _translate_frame(project, df_survey, lambda r: ("survey", r["name"]), rows)
    if df_choice is not None and {"list_name", "value"} <= set(df_choice.columns):
        df_choice = _translate_frame(
            project, df_choice, lambda r: ("choices", r["list_name"], r["value"]), rows
        )
    return df_survey, df_choice


def is_translated(df):
    return any(str(c).split("::")[0] in TRANSLATED_COLUMNS and "::" in str(c) for c in df.columns)
