# When a picture is insufficient

Use the installed Blender gate and one reviewable `bpy` script for the requested
facts. Retain its complete admission; do not attach to another owner's GUI or
install a live bridge. Verify actual Blender/API state rather than assuming an
external exporter exists. Return compact JSON and supporting views from the same
asset, scene and sampled frames; do not save changes to the source during inspection.

1. Record the source asset/scene identity and clean baseline before blaming motion.
   Inventory relevant objects, collections, parents, visibility, units and transforms.
   Separate character/prop geometry from controls or proxies; distinguish local
   from world bounds and original from evaluated geometry. Preserve the baseline.
2. For rigs, identify relevant rest/pose bones, parents, constraints and semantic
   left/right mappings. Establish forward/up/side from appropriate landmarks and
   root motion together; a neck-to-head vector usually measures up, not facing.
3. Sample first/mid/extreme frames and relevant contact, landing or turning
   intervals. Record frame rate, scale, ground definition and frame identifiers.
   Evaluate animation through Blender's dependency graph; bone origins alone do
   not measure deformed shoe/mesh contact.
4. Test the suspected failure: evaluated surface clearance for penetration, world
   displacement during known planted frames for sliding, semantic side ordering
   for crossover, and swing versus axial roll for twisting. Distinguish intended
   motion or scaling from import/constraint errors; compare with the clean baseline.
5. Report compact scene/rig identity, coordinate conventions and a frame/finding/
   measurement table. Separate measured failures from suspected causes and state
   what remains unverified. Corroborate relevant findings with suitable views.

Use tolerances from the project and source scale. Generic centimetre, percentage
or degrees-per-frame thresholds are prompts for investigation, not universal pass
criteria. Inspection does not authorize mesh edits, repair, deletion or baking.

Source inspiration: [ECC motion inspection](https://github.com/affaan-m/ecc/blob/main/skills/blender-motion-state-inspection/SKILL.md).
Use its structured-state workflow through local gate ownership; the standalone
Blender command shown upstream does not replace the installed gate launcher.
