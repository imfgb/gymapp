"""Per-page contextual hints.

A new user shouldn't have to guess what each screen is for. `page_hint`
injects a short Spanish tip for the current page (keyed by the resolved view
name) which `base.html` renders as a dismissible banner just under the nav.
Dismissal is remembered client-side in `localStorage` (no DB writes, fits the
no-jobs constraint) — once dismissed it never shows again.

Bump `HINTS_VERSION` to re-surface every hint after a meaningful rewrite.
"""

from __future__ import annotations

from django.http import HttpRequest

HINTS_VERSION = 1

# view_name -> (title, body). Only the pages a user actually browses to get a
# hint; POST/action endpoints are intentionally omitted.
PAGE_HINTS: dict[str, tuple[str, str]] = {
    "dashboard:home": (
        "Tu inicio",
        "Aquí ves tu entrenamiento de hoy, tu semana, tu bloque y tus PRs "
        "recientes. Empieza tu sesión desde la tarjeta de “Hoy”.",
    ),
    "dashboard:progress": (
        "Tu progreso",
        "Tendencia de volumen semanal, series por músculo y gráficas de tu "
        "composición corporal a lo largo del tiempo.",
    ),
    "routines:list": (
        "Rutinas",
        "Crea una rutina manual o genérala con un preset. Después prográmala "
        "en los días de la semana para que aparezca en tu inicio.",
    ),
    "routines:create": (
        "Crear rutina",
        "Elige un preset y tu estilo para autogenerarla con series y reps, o "
        "créala manual y agrega tus ejercicios uno por uno.",
    ),
    "routines:detail": (
        "Editar rutina",
        "Agrega días y ejercicios, ajusta series/reps/peso/descanso, y usa "
        "“Programar en la semana” para repartirla en tus días.",
    ),
    "routines:weekly_split": (
        "Tu semana",
        "Asigna qué día de tu rutina toca cada día de la semana. Usa “Llenado "
        "rápido” para repartir una rutina automáticamente.",
    ),
    "routines:block": (
        "Tu bloque",
        "Un plan de 6 semanas según tu estilo; la semana 6 es descarga. La "
        "semana actual se resalta sola según la fecha en que iniciaste.",
    ),
    "workouts:history": (
        "Tus entrenamientos",
        "El historial de tus sesiones. Si dejaste una en progreso puedes "
        "reanudarla, o revisar lo que hiciste en cada una.",
    ),
    "workouts:session": (
        "Sesión en curso",
        "Toca cada serie para completarla; el cronómetro de descanso arranca "
        "solo. Puedes cambiar, agregar o quitar ejercicios sobre la marcha.",
    ),
    "prs:list": (
        "Tus récords (PRs)",
        "Tu mejor peso por ejercicio y número de reps. Se detectan solos al "
        "terminar una sesión; también puedes agregarlos a mano.",
    ),
    "metrics:list": (
        "Tus métricas",
        "Registra tu peso y composición corporal. Con tu estatura calculamos "
        "tu BMI y dibujamos tu progreso en “Progreso”.",
    ),
    "metrics:profile": (
        "Tu perfil",
        "Tus datos base (estatura, fecha de nacimiento, sexo, estilo y "
        "objetivo). Afinan tus metas, tu nutrición y tus descansos.",
    ),
    "metrics:goals": (
        "Metas del mes",
        "Define cuántos entrenamientos quieres y tu peso objetivo del mes; "
        "abajo ves tu avance en barras.",
    ),
    "metrics:recovery": (
        "Recuperación",
        "Tu fatiga por músculo (decae con los días) y cómo amaneciste "
        "(sueño/estrés/dolor) se combinan en un consejo para hoy.",
    ),
    "nutrition:home": (
        "Nutrición",
        "Tus calorías y macros del día según tu perfil. Genera comidas con lo "
        "que te gusta, márcalas como comidas, y lleva tus suplementos.",
    ),
    "nutrition:preferences": (
        "Tus alimentos",
        "Marca lo que te gusta comer. Tus comidas se generan solo con esos "
        "alimentos — entre más marques, más variedad tendrás.",
    ),
    "nutrition:supplements": (
        "Suplementos",
        "Lleva control de tus suplementos del día. Se reinician cada día sin "
        "que tengas que hacer nada.",
    ),
    "injuries:list": (
        "Lesiones y prevención",
        "Registra una lesión y marca los ejercicios a evitar; te avisamos en "
        "la sesión y te sugerimos un reemplazo y movilidad.",
    ),
}


def page_hint(request: HttpRequest) -> dict:
    match = getattr(request, "resolver_match", None)
    view_name = getattr(match, "view_name", None) if match else None
    hint = PAGE_HINTS.get(view_name or "")
    if not hint:
        return {}
    title, body = hint
    return {
        "page_hint": {
            "key": f"hint:{view_name}:v{HINTS_VERSION}",
            "title": title,
            "body": body,
        }
    }
