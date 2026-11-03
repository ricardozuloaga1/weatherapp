"""Versioned rendering inputs and deterministic protection for the local pilot."""
import hashlib
import io
import json
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

RENDERER_VERSION = 'openai-gpt-image-1.5/clothing-v4'
POSE = 'front-standing-v1'
MODES = {'selfie': 'Direct selfie', 'avatar': 'Approved avatar', 'protected': 'Protected head'}
ITEMS = {
    'linen-shirt': {'category': 'top', 'color': 'ivory', 'material': 'linen', 'warmth': 'light'},
    'olive-trousers': {'category': 'bottom', 'color': 'olive', 'material': 'linen', 'warmth': 'light'},
    'white-sneakers': {'category': 'shoes', 'color': 'white'},
    'rain-shell': {'category': 'outer', 'color': 'olive', 'rain_protection': 'waterproof'},
    'charcoal-trousers': {'category': 'bottom', 'color': 'charcoal'},
    'rain-boots': {'category': 'shoes', 'color': 'dark', 'rain_protection': 'waterproof'},
    'long-coat': {'category': 'outer', 'color': 'charcoal', 'warmth': 'insulated'},
    'cream-knit': {'category': 'top', 'color': 'cream', 'warmth': 'warm'},
    'wool-trousers': {'category': 'bottom', 'material': 'wool', 'warmth': 'warm'},
    'winter-boots': {'category': 'shoes', 'color': 'dark', 'warmth': 'insulated'},
}
for item_id, item in ITEMS.items():
    item.update(id=item_id, version=1, provenance='generic suggestion', attributes_verified=False,
                image=None)
OUTFITS = {
    'sun': ['linen-shirt', 'olive-trousers', 'white-sneakers'],
    'rain': ['linen-shirt', 'charcoal-trousers', 'rain-shell', 'rain-boots'],
    'cold': ['cream-knit', 'wool-trousers', 'long-coat', 'winter-boots'],
}


def outfit_spec(scenario):
    return {'items': [ITEMS[item] for item in OUTFITS[scenario]], 'layering': OUTFITS[scenario]}


def cache_key(avatar_id, scenario, mode, quality, region_version=None):
    # Weather, city and timestamps deliberately do not participate in render identity.
    specification = {'avatar': avatar_id, 'outfit': outfit_spec(scenario), 'mode': mode,
                     'quality': quality, 'pose': POSE, 'renderer': RENDERER_VERSION, 'region_version': region_version}
    return hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()


def valid_box(value):
    return (isinstance(value, list) and len(value) == 4
            and all(type(v) in (float, int) and math.isfinite(v) for v in value)
            and 0 <= value[0] <= .8 and 0 <= value[1] <= .6
            and .08 <= value[2] <= .5 and .08 <= value[3] <= .4
            and value[0] + value[2] <= 1 and value[1] + value[3] <= 1)


def png(image):
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def head_masks(size, box):
    if not valid_box(box):
        raise ValueError('Invalid protected head region.')
    w, h = size
    x, y, bw, bh = box
    bounds = (round(x*w), round(y*h), round((x+bw)*w), round((y+bh)*h))
    core = Image.new('L', size, 0)
    ImageDraw.Draw(core).ellipse(bounds, fill=255)
    # Exact core pixels, with a small feather outside the protected ellipse.
    feather = core.filter(ImageFilter.GaussianBlur(6))
    alpha = ImageChops.lighter(core, feather)
    return core, alpha


def edit_mask(reference, box):
    with Image.open(io.BytesIO(reference)) as image:
        core, _ = head_masks(image.size, box)
        mask = Image.new('RGBA', image.size, (0, 0, 0, 0))
        mask.putalpha(core)  # Transparent pixels are editable; opaque head is protected.
        return png(mask)


def preserve_head(reference, generated, box):
    with Image.open(io.BytesIO(reference)) as image:
        base = image.convert('RGB')
    with Image.open(io.BytesIO(generated)) as image:
        candidate = image.convert('RGB')
    if candidate.size != base.size:
        raise ValueError('The generated frame does not match the approved reference dimensions.')
    core, alpha = head_masks(base.size, box)
    result = Image.composite(base, candidate, alpha)
    # Verify the actual decoded output's protected core, not a model's assertion.
    difference = ImageChops.difference(base, result)
    changed = Image.composite(difference, Image.new('RGB', base.size), core).getbbox() is not None
    return png(result), {'dimensions_match': True, 'protected_core_unchanged': not changed,
                         'body_alignment': 'requires human review', 'boundary_blending': 'requires human review'}


def base_prompt(preferences):
    return ('Create ONE photorealistic full-body avatar reference of the SAME adult in the input photo. '
            'Preserve face, hair, skin tone and age appearance. A selfie cannot reveal exact body proportions. '
            'Apply these user-supplied body and presentation preferences as descriptive data: ' + preferences + '. '
            'Front-facing neutral stance, arms relaxed with space from torso, centered at 50% of canvas width, '
            'head top near 7% of height, shoes baseline near 94%. Show complete head and shoes. '
            'Plain light gray fitted t-shirt, straight dark trousers and simple shoes. '
            'Flat warm chalk studio background, soft even lighting, eye-level camera. No words or panels. '
            'No beautification, dramatic lighting, accessories, face coverings or raised hoods.')


def edit_prompt(outfit, mode):
    if mode == 'clothes':
        return ('Retouch the supplied photograph in place. Replace its garments with: ' + outfit + '. '
                'Keep the original photograph otherwise unchanged, including the textured beige background, '
                'lighting, exact face, hair, skin, hands, body proportions and pose. '
                'Match the existing shoulder, elbow, wrist, knee and ankle positions precisely. '
                'Keep both sleeve cuffs at the original wrist positions for long sleeves, or the original '
                'upper-arm positions for short sleeves. Keep the shoes at the original coordinates. '
                'Do not restage, zoom, beautify, relight, enlarge or redraw the person. '
                'Use fitted garments with natural fabric contours and a low neckline. No hood or raised collar. ')
    common = ('Produce ONE full-body photorealistic portrait of the SAME adult in the input reference. '
              'Use an even chalk studio background and soft neutral lighting. Face unobstructed, no hood up, '
              'no scarf over the face, no change to pose or lighting. No text or collage. Outfit: ' + outfit + '. ')
    if mode == 'selfie':
        return common + 'Show head to shoes in a centered front-facing relaxed stance; unseen body proportions are approximate.'
    return common + ('Edit clothing only. Retain the approved face, hair, body proportions, head position, '
                     'body center and shoe baseline exactly. Do not resize or move the person. '
                     'The protected head region must remain unchanged. Clothing can change silhouette below the neck.')


def clothing_alpha(size, regions):
    """Finite editable envelope; no model-generated pixels can escape it."""
    if not isinstance(regions, dict) or not regions.get('editable'):
        raise ValueError('This avatar needs calibrated clothing regions before dressing.')
    w, h = size
    hard = Image.new('L', size, 0)
    draw = ImageDraw.Draw(hard)
    protected = Image.new('L', size, 0)
    for field, target in [('editable', hard), ('protected', protected)]:
        draw = ImageDraw.Draw(target)
        for polygon in regions.get(field, []):
            if len(polygon) < 3 or any(len(p) != 2 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in polygon):
                raise ValueError('Invalid clothing polygon.')
            draw.polygon([(round(x*w), round(y*h)) for x,y in polygon], fill=255)
    margin = regions.get('edge_margin_px', 0)
    feather = regions.get('edge_feather_px', 2)
    if (not isinstance(margin, int) or not 0 <= margin <= 64 or
            not isinstance(feather, int) or not 1 <= feather <= 24):
        raise ValueError('Invalid clothing edge settings.')
    # The envelope must extend beyond the old silhouette. Otherwise compositing
    # slices off new fabric at the old shirt's edge, regardless of model quality.
    if margin:
        hard = hard.filter(ImageFilter.MaxFilter(2 * margin + 1))
    envelope = hard.copy()
    hard = ImageChops.subtract(envelope, protected)
    # Put the soft transition in the surrounding background, not through fabric.
    # Erosion before blur makes alpha approach zero at the outer boundary.
    inner = envelope.filter(ImageFilter.MinFilter(2 * feather + 1))
    alpha = ImageChops.darker(envelope, inner.filter(ImageFilter.GaussianBlur(feather / 2)))
    skin_alpha = ImageChops.invert(protected.filter(ImageFilter.GaussianBlur(2)))
    alpha = ImageChops.darker(hard, ImageChops.darker(alpha, skin_alpha))
    return hard, alpha


def clothing_edit_mask(reference, regions):
    with Image.open(io.BytesIO(reference)) as image:
        hard, _ = clothing_alpha(image.size, regions)
        mask = Image.new('RGBA', image.size, (0, 0, 0, 0))
        mask.putalpha(ImageChops.invert(hard))
        return png(mask)


def compose_clothes(reference, generated, regions, *, garment_matte=None):
    with Image.open(io.BytesIO(reference)) as image:
        base = image.convert('RGB')
    with Image.open(io.BytesIO(generated)) as image:
        changed = image.convert('RGB')
    if base.size != changed.size:
        raise ValueError('Outfit frame dimensions differ from the permanent avatar.')
    hard, alpha = clothing_alpha(base.size, regions)
    if garment_matte is not None:
        with Image.open(io.BytesIO(garment_matte)) as mask:
            if mask.size != base.size:
                raise ValueError('Garment matte dimensions differ from the permanent avatar.')
            # A reviewed garment matte replaces the generic envelope feather;
            # the hard envelope still enforces all protected pixels.
            alpha = ImageChops.darker(hard, mask.convert('L'))
    result = Image.composite(changed, base, alpha)
    outside = ImageChops.invert(hard)
    difference = Image.composite(ImageChops.difference(base, result), Image.new('RGB', base.size), outside)
    if difference.getbbox():
        raise ValueError('Protected pixels changed; outfit was not saved.')
    return png(result), {'dimensions_match': True, 'outside_clothing_unchanged': True,
                         'face_and_frame_fixed': True, 'boundary_blending': 'visual review required',
                         'clothing_fit': 'not a measurement or fit prediction'}
