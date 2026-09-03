---
name: sd5-pe
description: Seedream 5.0 Pro image prompt spec — prompt structure (subject / style / lighting / composition / finish), the film vocabulary, and the working patterns for scene plates, storyboard grids, keyframes, palette control and edits.
models:
  - seedreamPro
  - seedream
tasks:
  - generate
---

# Seedream 5.0 Pro — prompt spec for film and short drama

Seedream 5.0 Pro covers three jobs in a production: **early visual assets** (scenes,
characters, storyboards, style references), **first frames and keyframes** for video, and
**post work** (relight, cleanup, colour, layer splits).

---

## THE ADHERENCE RULE — read this before the rest

This spec is a **grammar, not a content source**. It tells you how to arrange and phrase
what the writer asked for. It never authorises you to invent subject matter.

- Every noun, adjective and named thing in the writer's request appears in the output.
- If the writer did not state the lighting, **say nothing about the lighting.** The same
  for time of day, weather, colour grade, lens, camera height, mood and season.
- An empty slot is a legitimate output. A prompt of one clause is a legitimate output.
- Never add people, animals, vehicles, props or architecture that were not asked for.
- Never reach for the vocabulary below to fill a gap. It exists to phrase a stated
  intention precisely, not to decorate an unstated one.

"Photorealistic forest with tall oak trees" is a complete prompt. It does not want golden
hour, volumetric god rays, a winding path or a lone figure.

---

## Prompt structure

Order the parts the model reads best, and **include only the parts the writer supplied**:

1. **Subject** — appearance, state, motion, expression, attire, and the other details
   that identify it. Be concrete about what a camera would see.
2. **Style** — the artistic register: film still, cyberpunk, minimalism, anime, matte
   painting, and so on.
3. **Lighting** — direction, quality (hard / soft), colour temperature, time (golden
   hour, night neon), and what the light is doing to the subject.
4. **Composition** — shot size (close-up / medium / long / extreme long), viewing angle
   (high / low / eye level), and method (symmetrical, diagonal, rule of thirds).
5. **Finish** — grain, halation, bokeh shape, black level, colour grading, resolution.

A production prompt often reads as short declarative sentences separated by periods
rather than one long clause chain. Both work; the sentence form is easier to edit.

## Reference images

For multi-image fusion, style transfer, outfit transfer and identity work, attach the
references rather than describing them — fidelity comes from the pixels, not the adjectives.
Cite them positionally in the prompt so each reference is bound to the words it governs.

---

## Vocabulary

Reach for these ONLY to phrase something the writer stated.

**Register** — cinematic live-action, photorealistic film still, high-end feature film
look, epic live-action fantasy cinema, realistic matte photography, hyper-realistic,
premium production design, documentary realism, illustration, matte painting.

**Lens and finish** — anamorphic, wide cinematic frame, 2.39:1 widescreen, warm grain,
soft halation, oval bokeh, deep blacks, shallow depth of field, natural lens perspective,
high-resolution detail, realistic colour grading, 8K cinematic realism.

**Light** — soft cinematic lighting, hard directional light, low-key, high-contrast
silhouettes, volumetric beams, god rays cutting through haze, practical lantern glow,
tungsten bulb as the primary source, magic hour, golden-hour light from the right,
pale winter sky, physically accurate lighting, atmospheric depth.

**Shot terms** — ELS (extreme long shot), LS (long shot), MS (medium), MCU (medium
close-up), CU (close-up), ECU (extreme close-up), OTS (over-the-shoulder two-shot),
top-down / bird's-eye, low angle, eye level.

**Materials** — realistic wood grain, chisel-marked sandstone, Carrara marble with grey
veining, weathered ancient walls, wet reflective surfaces, frost-covered stone, patina.

---

## Patterns that work

### Scene plate — a location as production design

Lead with the register and the viewpoint, then the architecture and its materials, then
the light, then the finish.

> Cinematic live-action style top-down floor plan layout, bird's-eye view of a traditional
> Japanese imperial courtyard, shot as a high-end film production design visualization.
> Camera looking straight down with precise architectural clarity. Symmetrical courtyard
> composition with a central pond, wooden pavilions connected by covered walkways, lush
> maple and pine gardens, subtle practical lantern glow, natural material textures,
> realistic wood grain and stone surfaces. Soft cinematic lighting, atmospheric depth,
> premium production design, photorealistic architectural set, high-resolution detail,
> clear spatial arrangement, film still quality, realistic colour grading.

### Storyboard grid — many shots in one image

Seedream will render a labelled grid. State the grid size, the style and mood once, then
number each frame and lead it with its shot term.

> A 3x3 cinematic storyboard grid in live-action film still style inspired by the visual
> language of Blade Runner 2049: neon-noir futurism, rain-soaked megacity streets, vast
> brutalist architecture, holographic advertisements, dense atmospheric haze, blue and
> amber light contrast, volumetric beams cutting through smoke, wet reflective surfaces,
> high-contrast silhouettes, moody low-key cinematography. Each frame clearly labeled with
> its cinematography shot term:
> 1 ELS / Extreme Long Shot: a colossal futuristic city skyline at night, endless towers
> disappearing into blue haze, enormous amber holograms glowing above rain-soaked streets.
> 2 LS / Long Shot: a lone figure crossing a flooded plaza…

### Keyframe — a frame built to hand to a video model

Open with the **format line** (frame, lens, finish), then the **space**, then the
**figures**. This order is what makes the frame hold depth and scale when it is animated.

> Wide cinematic frame, anamorphic, warm grain, soft halation, oval bokeh, deep blacks,
> hyper-realistic.
> Interior, narrow stone stairwell. Rough-cut sandstone block walls climb the full height
> of the frame, every brick textured with chisel marks, age and patina. Warm amber tones
> in the stone where the light catches, cool grey-blue shadows in the recesses. A thin
> wrought-iron handrail runs diagonally from lower left to upper right. A single bare bulb
> hangs from a black cord in the upper right, glowing warm tungsten, the primary light
> source for the entire frame.
> Isaak stands mid-stride on the stone steps, captured in profile facing right…

A first frame that establishes **depth, light direction and character scale** produces a
better video than one that is merely a clean picture. Give the camera somewhere to go.

### Colour and palette control

Name the hexes. Seedream honours an explicit palette.

> …the overall colour scheme strictly follows Mauve Dust #CB96BA, Bluebell Frost #B0B3D6,
> Venus Flower #E0E4E7, Green Beryl #D0DDC4, Duck Egg #9BBCAC, Forest Frolic #77A39A,
> presenting a gentle, dreamy, French retro film atmosphere.

To pin the register against a palette, say what it is NOT:

> The visual style must be realistic live-action cinema, not illustration: photographed
> with a high-end cinema camera, natural lens perspective, physically accurate lighting.

### Edits — change only what you name

An edit prompt is a list of change-only clauses against the attached image. Region boxes
are supported and make a removal unambiguous.

> Remove the pedestrians in the background at Figure 1 `<bbox>3 448 287 750</bbox>` and
> Figure 1 `<bbox>671 466 888 766</bbox>`. Add more snow accumulation on the road in
> Figure 1 `<bbox>11 602 986 990</bbox>`.

Relight, colour grade and layer/asset splits follow the same shape: name the change, name
nothing else, and everything unnamed is preserved.

---

## Stability checklist

Before returning a prompt, confirm:

- Every content word the writer supplied is present.
- Nothing is present that the writer did not supply.
- The subject is described as a camera would see it, not as an idea.
- Where the writer named a style, lighting, composition or palette, it is stated
  concretely rather than gestured at.
- No slot has been filled with default cinematic garnish.
