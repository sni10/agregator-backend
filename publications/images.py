"""An uploaded photo -> WebP variants in MEDIA_ROOT. Pillow decodes it here, so a file that is not a real image
(or a decompression bomb) is refused before anything is stored."""
import io

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image as Pillow, ImageOps

from .models import Image

WIDTHS = (1200, 600, 320)  # story page, tiles, small tiles; the front builds srcset from them
RATIO = (16, 9)
FORMATS = {'JPEG', 'PNG', 'WEBP'}
MIN_WIDTH = 600  # smaller looks blurry on the story page
MAX_PIXELS = 40_000_000
QUALITY = 80

Pillow.MAX_IMAGE_PIXELS = MAX_PIXELS


class BadImage(ValueError):
    pass


def save_image(file, meta: dict) -> Image:
    """The stored image with this external_id, or a new one made from `file`. The same photo is processed once."""
    if existing := Image.objects.filter(external_id=meta['external_id']).first():
        return existing
    picture = _open(file)
    if picture.width < MIN_WIDTH:
        raise BadImage(f'{picture.width} px wide: at least {MIN_WIDTH} needed')
    image = Image(**meta)
    sizes = [(width, width * RATIO[1] // RATIO[0]) for width in WIDTHS if width <= picture.width]
    for width, height in sizes:
        variant = ImageOps.fit(picture, (width, height), Pillow.Resampling.LANCZOS)
        name = image.file_name(width)
        default_storage.delete(name)  # left over from an upload that failed halfway
        default_storage.save(name, ContentFile(_webp(variant)))
    image.width, image.height = sizes[0]
    image.save()
    return image


def variants(image: Image) -> list[tuple[int, str]]:
    """(width, URL) of the stored variants, largest first."""
    return [(width, default_storage.url(image.file_name(width))) for width in WIDTHS if width <= image.width]


def _open(file) -> Pillow.Image:
    try:
        with Pillow.open(file) as checked:
            checked.verify()
        file.seek(0)
        picture = Pillow.open(file)
        if picture.format not in FORMATS:
            raise BadImage(f'{picture.format} is not accepted: {", ".join(sorted(FORMATS))}')
        return ImageOps.exif_transpose(picture).convert('RGB')
    except (OSError, SyntaxError, Pillow.DecompressionBombError) as exc:
        raise BadImage(f'not a usable image: {exc}') from exc


def _webp(picture: Pillow.Image) -> bytes:
    buffer = io.BytesIO()
    picture.save(buffer, 'WEBP', quality=QUALITY, method=6)
    return buffer.getvalue()
