---
name: sd-editing
description: Seedance video editing — instruction editing, editing with reference images, and audio editing. Adds, removes or modifies visual and audio elements in an existing video, with timestamps to say when an edit takes effect.
models:
  - seedance25
  - seedance
  - seedanceFast
  - seedanceMini
tasks:
  - edit
---

# Seedance Video Editing

## Trigger keywords in the prompt

The task is routed by what the prompt SAYS. It must read as an instruction to change an existing video, using one of: **edit video, add, insert, remove, delete, modify, replace, change to**, or a plainly related instruction.

Reference the source and any target material by their numbered handles — `@video1`, `@image1`, `@audio1` — in the instruction itself:

> Add small animals to `@video1`; replace the character in `@video1` with `@image1`; remove the background music from `@video1`.

A prompt that only describes a desired result, without naming the source and the change, is not an edit — it is a new generation.

## The three editing tasks

### 1. Video instruction editing

Text instructions add, remove or modify visual elements in a video. **Timestamps are supported** to say when an edit takes effect.

- **Add** — subjects, costumes, camera movements, special effects, and more.
- **Modify** — the subject, parts of the subject, style, background, colour, lighting, material, motion, **camera position**, and more.
- **Remove** — subjects, subtitles, watermarks, and more.

### 2. Video editing with reference images

Text instructions **plus reference images** add, remove or modify visual elements. The images are the target material — what an addition or replacement looks like. Cite them as `@image1 … @imageN`, and say what each contributes. Timestamps are supported here too.

### 3. Audio editing

Adds, removes or modifies audio in the video.

- **Add** — vocals, music, sound effects, and more.
- **Modify** — vocals, music, sound effects, and more.
- **Remove** — vocals, music, sound effects, and more.

## Writing the instruction

- Name the source (`@video1`), the operation, and the target — in that order — for each change.
- Several changes may ride in one prompt, separated by semicolons.
- Use a timestamp when the change belongs to a moment rather than the whole clip.
- Say what must NOT change when a change could reasonably spread: everything you do not name is expected to stay as it is in the source.
- Aspect ratio and duration are inherited from the source. Never write them into the prompt.
