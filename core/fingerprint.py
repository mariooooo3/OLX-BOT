"""Amprenta de browser (fingerprint) a unui cont — deterministica, derivata
din profilul lui de browser.

De ce deterministica si nu aleatoare la fiecare pornire: un cont real are un
dispozitiv stabil. Daca amprenta s-ar schimba la fiecare repornire a botului,
ar parea ca acelasi "om" foloseste un laptop nou de fiecare data — semnal la
fel de suspect ca amprenta identica intre conturi diferite. In schimb, aici
alegem componentele o singura data, pe baza hash-ului caii profilului de
browser — acelasi profil = aceeasi amprenta, mereu, in orice proces
(dashboard, container Docker, fereastra de login manual).

De ce dupa profile_dir si nu dupa account_id: login.py (care deschide
fereastra de login manual) si BrowserClient (care ruleaza botul, eventual
intr-un container separat) trebuie sa foloseasca EXACT aceeasi amprenta
pentru acelasi cont — altfel sesiunea creata la login ar parea, din
perspectiva OLX, un dispozitiv diferit fata de cel care trimite mesajele.
profile_dir e singurul identificator pe care il au ambele (login.py nu
primeste intotdeauna account_id, dar primeste mereu --profile).

De ce componente independente si nu un pool fix de profiluri complete: cu
putine profiluri complete (ex. 8), doua conturi ale aceluiasi user coliziona
des (~12% sansa la fiecare pereche — verificat empiric). Combinand 3
componente alese INDEPENDENT (viewport x versiune Chrome x placa video),
spatiul creste la sute de combinatii, fara sa strice coerenta interna a
fiecarei amprente (Windows + Chrome + randare Direct3D11 raman mereu
impreuna — un user-agent Windows cu semnatura WebGL de Mac ar fi el insusi
o discrepanta usor de detectat).
"""
import hashlib
from pathlib import Path

# Rezolutii desktop tipice, cu factorul de scalare cu care apar de obicei in
# lumea reala (ecrane HiDPI mai des la rezolutii mari).
_VIEWPORTS = [
    {"width": 1366, "height": 768, "device_scale_factor": 1},
    {"width": 1920, "height": 1080, "device_scale_factor": 1},
    {"width": 1536, "height": 864, "device_scale_factor": 1.25},
    {"width": 1440, "height": 900, "device_scale_factor": 1},
    {"width": 1600, "height": 900, "device_scale_factor": 1},
    {"width": 1280, "height": 720, "device_scale_factor": 1},
    {"width": 1920, "height": 1200, "device_scale_factor": 1},
    {"width": 1536, "height": 960, "device_scale_factor": 1},
    {"width": 1680, "height": 1050, "device_scale_factor": 1},
    {"width": 2560, "height": 1440, "device_scale_factor": 1.5},
]

# Versiuni Chrome plauzibile, recente — doar numarul "major" conteaza pentru
# credibilitate (minor/build fixe, ca la orice build stabil real).
_CHROME_VERSIONS = [
    "127.0.0.0", "128.0.0.0", "129.0.0.0", "130.0.0.0", "131.0.0.0",
    "132.0.0.0", "133.0.0.0", "134.0.0.0",
]

# vendor+renderer ca PERECHE ATOMICA — niciodata amestecate intre ele, ca sa
# nu apara o combinatie incoerenta (placa NVIDIA cu renderer AMD etc.)
_GPUS = [
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce MX250 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3050 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon(TM) RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon(TM) Vega 8 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]

_UA_TEMPLATE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{version} Safari/537.36"
)


def _identity(profile_dir: str | Path) -> str:
    """Cheia stabila a unui profil, identica pe Windows si Linux — vezi
    account_profile_dir() din core/accounts.py pentru acelasi motiv."""
    return Path(profile_dir).as_posix()


def _index(profile_dir: str | Path, salt: str, size: int) -> int:
    """Index determinist in [0, size), independent intre componente diferite
    (salturi diferite) — asa se evita ca viewport/versiune/placa video sa
    varieze mereu "impreuna" pentru profiluri cu hash-uri apropiate."""
    key = f"{_identity(profile_dir)}:{salt}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return int(digest, 16) % size


def _canvas_seed(profile_dir: str | Path) -> int:
    key = f"{_identity(profile_dir)}:canvas".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return int(digest, 16) % (2**31 - 1)


def profile_for(profile_dir: str | Path) -> dict:
    """Amprenta (user-agent, viewport, placa video "raportata") a acestui
    profil de browser — mereu aceeasi pentru acelasi profile_dir."""
    viewport = _VIEWPORTS[_index(profile_dir, "viewport", len(_VIEWPORTS))]
    version = _CHROME_VERSIONS[_index(profile_dir, "chrome_version", len(_CHROME_VERSIONS))]
    vendor, renderer = _GPUS[_index(profile_dir, "gpu", len(_GPUS))]
    return {
        "user_agent": _UA_TEMPLATE.format(version=version),
        "viewport": {"width": viewport["width"], "height": viewport["height"]},
        "device_scale_factor": viewport["device_scale_factor"],
        "webgl_vendor": vendor,
        "webgl_renderer": renderer,
    }


def init_script_for(profile_dir: str | Path) -> str:
    """Script JS injectat in fiecare pagina a contextului (context.add_init_script),
    inainte sa ruleze orice cod al paginii — patcheaza:
      - navigator.webdriver (semnul clasic de automatizare)
      - WEBGL vendor/renderer (sa corespunda cu placa video "raportata")
      - un zgomot minuscul, dar STABIL, pe canvas — suficient cat sa nu mai
        fie identic byte-cu-byte cu al altui cont, fara sa strice randarea
    """
    profile = profile_for(profile_dir)
    canvas_seed = _canvas_seed(profile_dir)
    return f"""(() => {{
  try {{
    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
  }} catch (e) {{}}

  try {{
    const VENDOR = {profile["webgl_vendor"]!r};
    const RENDERER = {profile["webgl_renderer"]!r};
    const UNMASKED_VENDOR_WEBGL = 37445;
    const UNMASKED_RENDERER_WEBGL = 37446;
    for (const proto of [
      window.WebGLRenderingContext && window.WebGLRenderingContext.prototype,
      window.WebGL2RenderingContext && window.WebGL2RenderingContext.prototype,
    ]) {{
      if (!proto || !proto.getParameter) continue;
      const original = proto.getParameter;
      proto.getParameter = function (param) {{
        if (param === UNMASKED_VENDOR_WEBGL) return VENDOR;
        if (param === UNMASKED_RENDERER_WEBGL) return RENDERER;
        return original.apply(this, arguments);
      }};
    }}
  }} catch (e) {{}}

  try {{
    // generator pseudo-aleator mic, determinist (mulberry32) — acelasi seed
    // produce mereu acelasi zgomot pentru acest profil
    let seed = {canvas_seed};
    function rand() {{
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }}
    const noisify = (canvas) => {{
      const ctx = canvas.getContext('2d');
      if (!ctx || canvas.width === 0 || canvas.height === 0) return;
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < data.data.length; i += 4) {{
        if (rand() < 0.0005) data.data[i] = data.data[i] ^ 1;
      }}
      ctx.putImageData(data, 0, 0);
    }};
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function (...args) {{
      try {{ noisify(this); }} catch (e) {{}}
      return origToDataURL.apply(this, args);
    }};
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function (...args) {{
      const result = origGetImageData.apply(this, args);
      try {{
        for (let i = 0; i < result.data.length; i += 4) {{
          if (rand() < 0.0005) result.data[i] = result.data[i] ^ 1;
        }}
      }} catch (e) {{}}
      return result;
    }};
  }} catch (e) {{}}
}})();"""
