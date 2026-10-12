"""Decode once, strip metadata, preserve full oriented frame. No file paths.

Immutable BLOB assets are separate from WorldState in the same transactional DB.
The database is the existing application's single-user security boundary.
"""
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES=10*1024*1024
MAX_SOURCE_PIXELS=32_000_000
MIN_SIDE=256
MAX_SIDE=4096
FORMATS={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}


def normalized_size(width, height):
    """Choose one proportional scale; integer pixel rounding is unavoidable."""
    short, long = min(width,height), max(width,height)
    if short < 1 or width*height > MAX_SOURCE_PIXELS:
        raise ValueError('Исходное изображение слишком большое: максимум 32 миллиона пикселей.')
    if long*MIN_SIDE > short*MAX_SIDE:
        raise ValueError('Слишком вытянутое изображение: невозможно получить стороны 256–4096 px без обрезки или искажения.')
    scale = MAX_SIDE/long if long > MAX_SIDE else MIN_SIDE/short if short < MIN_SIDE else 1
    return round(width*scale),round(height*scale)


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
                normalized_size(w,h)  # Bound original resources BEFORE decoding/resizing.
                if getattr(image,'n_frames',1)!=1: raise ValueError('Нужно неподвижное изображение.')
                image.verify()
            with Image.open(BytesIO(content),formats=[expected]) as image:
                normalized=ImageOps.exif_transpose(image)
                normalized.load()
                clean=Image.new('RGBA' if ('A' in normalized.getbands() or 'transparency' in normalized.info) else 'RGB',normalized.size)
                clean.paste(normalized.convert(clean.mode))
                target=normalized_size(*clean.size)
                if target != clean.size:
                    clean=clean.resize(target,resample=Image.Resampling.LANCZOS)
                out=BytesIO();clean.save(out,format='PNG')
                return out.getvalue(),clean.width,clean.height
    except (UnidentifiedImageError,OSError,SyntaxError,MemoryError,OverflowError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('Повреждённое или небезопасное изображение.') from exc
