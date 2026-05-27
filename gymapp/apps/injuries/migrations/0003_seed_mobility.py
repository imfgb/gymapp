"""Seed a small curated mobility / corrective library.

These are deliberately conservative, well-known moves — short instructions, no
external video URLs (those rot). The user can extend the catalogue from
`/admin/` later.
"""

from django.db import migrations


SEEDS = [
    # Shoulder
    ("band-pull-apart", "Band pull-apart", "shoulder",
     "3 series de 15 con banda elástica. Brazos extendidos al frente, separa horizontalmente apretando escápulas."),
    ("wall-slides", "Wall slides", "shoulder",
     "3 series de 10. Espalda y brazos pegados a la pared, sube y baja los antebrazos manteniendo contacto."),
    ("scapular-pushup", "Scapular push-up", "shoulder",
     "3 series de 10. En posición de lagartija, solo retrae y protrae la escápula sin doblar codos."),
    # Lower back / lumbar
    ("cat-camel", "Cat-camel", "lower_back",
     "2 minutos. En cuadrupedia, alterna lomo arqueado (gato) y deprimido (camello) con respiración lenta."),
    ("birddog", "Bird-dog", "lower_back",
     "3 series de 10 por lado. En cuadrupedia, extiende brazo y pierna opuestos manteniendo core firme."),
    ("dead-bug", "Dead bug", "lower_back",
     "3 series de 10 por lado. Boca arriba, baja brazo y pierna opuestos sin que la lumbar se despegue del piso."),
    ("90-90-hip", "90/90 hip rotation", "lower_back",
     "5 minutos. Sentado con piernas en 90/90, gira la cadera de un lado a otro lento, controlando el rango."),
    # Hip
    ("hip-flexor-stretch", "Estiramiento de psoas (medio arrodillado)", "hip",
     "3 series de 30 s por lado. Rodilla atrás, tuck pélvico, inclínate hacia adelante hasta sentir el flexor."),
    ("90-90-hip-2", "90/90 movilidad de cadera", "hip",
     "3 minutos. Sentado en 90/90, levanta la rodilla de atrás y gira al otro lado, alternando."),
    ("glute-bridge", "Puente de glúteo", "hip",
     "3 series de 12. Boca arriba con rodillas dobladas, sube cadera apretando glúteos al final del rango."),
    # Knee
    ("terminal-knee-ext", "Terminal knee extension (con banda)", "knee",
     "3 series de 15 por pierna. Banda detrás de la rodilla, extiende el último tramo apretando cuádriceps."),
    ("vmo-squat-iso", "Iso wall sit", "knee",
     "3 series de 30 s. Espalda en la pared, rodillas a 90°, mantén apretando cuádriceps."),
    # Ankle
    ("ankle-cars", "Ankle CARs", "ankle",
     "2 series de 8 por lado. Movimiento circular controlado del tobillo en todo el rango disponible."),
    ("calf-raise-eccentric", "Calf raise excéntrico", "ankle",
     "3 series de 10. Sube en dos pies, baja en uno lentamente (5 s). Trabaja la fascia y el tendón de Aquiles."),
    # Neck / upper back
    ("chin-tuck", "Chin tuck", "neck",
     "3 series de 10. Lleva la barbilla hacia atrás (no abajo) creando doble papada; mantén 2 s."),
    ("thoracic-extension", "Extensión torácica sobre foam roller", "upper_back",
     "5 minutos. Foam roller bajo escápulas, abre los brazos al cielo y respira profundo."),
    # Elbow / wrist
    ("wrist-flexor-stretch", "Estiramiento de flexores de muñeca", "wrist",
     "3 series de 30 s. Brazo extendido, palma arriba, jala los dedos hacia abajo con la otra mano."),
    ("forearm-pronation", "Pronación / supinación con peso", "elbow",
     "3 series de 12 por brazo. Mancuerna o martillo ligero; gira la muñeca lento en ambas direcciones."),
]


def seed(apps, schema_editor):
    MobilityExercise = apps.get_model("injuries", "MobilityExercise")
    for slug, name, region, instructions in SEEDS:
        MobilityExercise.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "body_region": region,
                "instructions": instructions,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    MobilityExercise = apps.get_model("injuries", "MobilityExercise")
    MobilityExercise.objects.filter(slug__in=[s[0] for s in SEEDS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("injuries", "0002_mobilityexercise"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
