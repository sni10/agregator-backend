"""Markdown from the pipeline or the admin -> HTML the site can show as is. HTML in the input is never trusted:
it is rendered, then everything outside the allowlist is stripped (nh3)."""
import markdown as markdown_lib
import nh3

TAGS = {'p', 'br', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'blockquote', 'h2', 'h3', 'code', 'pre'}
ATTRIBUTES = {'a': {'href'}}
URL_SCHEMES = {'http', 'https'}


def render(text: str) -> str:
    html = markdown_lib.markdown(text, output_format='html')
    return nh3.clean(html, tags=TAGS, attributes=ATTRIBUTES, url_schemes=URL_SCHEMES,
                     link_rel='nofollow noopener noreferrer')
