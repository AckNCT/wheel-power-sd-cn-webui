from PIL import Image
from io import BytesIO
import os
from base64 import b64encode, b64decode

def pil_image_to_png_bytesio(im):
    bio = BytesIO()
    im.save(bio, format="PNG")
    return bio
    
def pil_image_to_png_bytes(im):
    return pil_image_to_png_bytesio(im).getvalue()
    
def cairo_svg_surface_to_png(svg_surface, fmt, alpha_channel=True):
    """
    @param format: Format of output PNG.
                None - Do nothing
                "pil" - PIL image.
                "bytes" - Raw PNG bytes
                <file_path> - Save as PNG file instead of returning it
    """
    bio = BytesIO()
    svg_surface.write_to_png(bio)
    im = None
    if not alpha_channel:
        im = Image.open(bio).convert("RGB")
    
    if fmt == "bytes" or fmt is bytes:
        if im is not None:
            bio = pil_image_to_png_bytesio(im)
        return bio.getvalue()
    elif fmt.upper() == "PIL":
        if im is not None:
            return im
        bio.seek(0)
        return Image.open(bio)
    elif fmt and isinstance(fmt, str):
        dirpath = os.path.dirname(fmt)
        if not dirpath or os.path.isdir(dirpath):
            if im is not None:
                bio = pil_image_to_png_bytesio(im)
            open(fmt, "wb").write(bio.getvalue())
            
def image_file_as_png_bytes(fpath):
    png_image = Image.open(fpath)
    bio = BytesIO()
    png_image.save(bio, format="png")
    png_raw = bio.getvalue()
    return png_raw
    
def image_b64_to_pil(image_b64):
    if image_b64 is None:
        return image_b64
    return Image.open(BytesIO(b64decode(image_b64)))