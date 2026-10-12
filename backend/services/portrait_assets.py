"""Decode once, strip metadata, preserve full oriented pixels. No file paths.

Immutable BLOB assets are separate from WorldState in the same transactional DB.
The database is the existing application's single-user security boundary.
"""
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES=10*1024*1024
FORMATS={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}


def decode_image(content, mime):
    if len(content)>MAX_BYTES or not content: raise ValueError('Изображение должно быть не больше 10 MiB.')
    expected=FORMATS.get(mime)
    if expected is None: raise ValueError('Поддерживаются PNG, JPEG и WebP.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(content),formats=[expected]) as image:
                if image.format!=expected: raise ValueError('Содержимое не соответствует типу изображения.')
                w,h=image.size
                if not (256<=w<=4096 and 256<=h<=4096) or w*h>4096**2:
                    raise ValueError('Размер изображения: от 256×256 до 4096×4096.')
                if getattr(image,'n_frames',1)!=1: raise ValueError('Нужно неподвижное изображение.')
                image.verify()
            with Image.open(BytesIO(content),formats=[expected]) as image:
                normalized=ImageOps.exif_transpose(image)
                normalized.load()
                clean=Image.new('RGBA' if ('A' in normalized.getbands() or 'transparency' in normalized.info) else 'RGB',normalized.size)
                clean.paste(normalized.convert(clean.mode))
                out=BytesIO();clean.save(out,format='PNG')
                return out.getvalue(),clean.width,clean.height
    except (UnidentifiedImageError,OSError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('Повреждённое или небезопасное изображение.') from exc
