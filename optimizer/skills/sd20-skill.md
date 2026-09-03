---
name: sd20-pe
description: Seedance 2.0 prompt spec — the finished prompt structure Compose returns, the official Dreamina Seedance 2.0 prompt guide (core formula, image/audio/video reference syntax, text rendering, editing and extension), and the Vibe Creating method for distilling user input.
models:
  - seedance
  - seedanceFast
  - seedanceMini
---

# Seedance 2.0 Prompt Spec

## Part 0 — The Finished Prompt

When the caller asks for a prompt, return the prompt and nothing else — no judgement line, no action label, no notes section. Lay it out in this order, omitting any block the shot has nothing for. Never pad a block to look complete.

1. **Subject and reference definitions** — one sentence per identity-bearing reference, in the guide's own syntax:
   `Use the woman from Image 1 and Image 2, maintaining consistent facial features and clothing.`
   `Refer to the layout of the pine clearing in Image 3; do not use the people in it.`
   `Refer to the storyboard composition in Image 6, presenting its frames in the predefined order.`

2. **Media binding** — one sentence per attached audio or video reference:
   `The woman speaks with the voice of Audio 1.`
   `Refer to the camera movement in Video 1, keeping the cinematography consistent.`

3. **The shot body** — the events in order, written to the guide's core formula: **subject + motion + environment + camera movement/cut + aesthetic + audio**. One `Shot N:` block per shot when the piece has several; a single shot needs no label. Address every subject by its Image number.

4. **Look** — one sentence for style, grade and texture, when the material states one.

5. **Constraint tail** — close with: `HD, cinematic texture, natural colors. Keep it subtitle-free, avoid generating any text or subtitles. Do not generate watermarks or logos. Do not generate duplicate characters.` Omit the subtitle clause when the shot deliberately renders text or subtitles.

Hard rules for this model:

- **NO first-frame or last-frame language.** Seedance 2.0 has no keyframe control. Never write that the shot opens on, passes through or ends on the composition of an image. Ordered composition comes only from a storyboard reference image, as Part 1 describes.
- **NO timestamps.** Write plain event-order prose; the sequence of events carries the time.
- **Never invent a reference number.** Cite only images, audio and video that are actually attached.
- **Aspect ratio, duration, resolution and the audio toggle are parameters, not prompt text.**

## Part 1 — Official Dreamina Seedance 2.0 Prompt Guide

## Basic Prompting Techniques

Dreamina Seedance 2.0  boasts exceptional **semantic understanding** and **multimodal interaction** capabilities. To create high-quality videos, we recommend focusing your instructions on the following dimensions. The model is designed to precisely capture and reconstruct every detail provided:



### The Core Prompt Formula

Dreamina Seedance 2.0 excels at following **natural language logic**. You can flexibly combine the following elements based on your creative needs:

**Subject + Motion + Environment (Optional) + Camera Movement/Cut (Optional) + Aesthetic Description (Optional) + Audio (Optional)**

**Subject + Motion + Environment (Optional) + Camera Movement/Cut (Optional) + Aesthetic Description (Optional) + Audio (Optional)**

- **Subject + Motion:** The logical foundation of your generation. Clearly define **"Who"** is performing **"What action."**

- **Environment + Aesthetics:** Define the overall tone by describing the spatial background, lighting details, or specific visual styles.

- **Audio:** Advanced instructions can include **ambient sound effects** to achieve an immersive, synchronized audiovisual output.

### Multimodal Reference & Control

Beyond text descriptions, you can "feed" visual or auditory assets to lock in the** ideal baseline state** for your video. Dreamina Seedance 2.0 supports deep referencing across images, audio, and video:

- **Explicit Referencing:** Clearly specify the reference source within your prompt (e.g., *"Use the composition of Image 1"* or *"Match the motion of Video 2"*).

- **Precision Transfer:** The model automatically extracts core features from the reference material and merges them with your text. This ensures the output maintains high fidelity and predictability while still allowing for creative variation.


### Text Rendering

Dreamina Seedance 2.0 supports generating common text across multiple scenarios, including **T2V (Text-to-Video)**, **I2V (Image-to-Video)**, **R2V (Reference-to-Video)**, and **V2V (Video-to-Video)**.

- **Key Capabilities:**

    - **Intelligent Adaptation:** The model automatically matches font styles and colors to the specific context of your scene for seamless visual integration.

    - **Granular Control:** You can explicitly define the following attributes within your prompts:

        - **Style:** Color and font style.

        - **Dynamic Behavior:** How the text appears (entrance style) and the specific timing of its appearance.

        - **Layout:** Precise positioning within the frame.

- **Best Practices****：**

    - **Use Common Vocabulary:** Use widely recognized words and familiar phrases. The model performs best with standard English lexicon.

    - **Avoid Rare or Obscure Words:** High-complexity or "dictionary-deep" words may lead to inconsistencies. Simpler, high-frequency words ensure higher rendering accuracy.

    - **Minimize Special Symbols:** Limit the use of complex symbols or non-standard punctuation to maintain visual clarity and font fidelity.

#### Slogan

- **Prompt Techniques**

    - **1. The Universal Formula**

        - To achieve precise text rendering as you wish, structure your prompt as follows:

            - ***[Text Content] + [Timing] + [Positioning] + [Entrance/Appearance Style], [Visual Attributes (Color, ******Font Style******)]***

    - **2. Visual Style & Consistency**

        - **Contextual Adaptation:** Dreamina Seedance 2.0 automatically identifies the scene's context to match the most appropriate font aesthetic.

        - **Precision Requirements:** If your project requires strict adherence to specific visual standards (e.g., brand consistency), please refer to section **[2****.2.2 Multi-Image Reference: Logo Reference]** for advanced guidance.

#### Subtitle

- **Common Syntax:**

    - ***Display subtitles at the bottom-center with the text. The subtitles must be perfectly synchronized with the audio rhythm and pacing.***


#### Speech Bubble

- **Common Syntax：**

    - ***[Character] says, "[Dialogue]." Speech bubbles appear around the character containing the spoken text.***

### **Image Reference**

> Dreamina Seedance 2.0 supports **multi-perspective references** for subjects, as well as **multi-image referencing** for scene layouts, storyboards, and more.
> 
> If your creative process requires a specific order (e.g., for storyboarding or sequential motion), please **upload your images in the desired sequence**. You can then use specific identifiers in your prompt for precise control:
> 
> - **Syntax:** Refer to **"Image 1," "Image 2," ... "Image N"** to accurately map each reference to your instructions.

- Simply identify the reference objects clearly. The model can process instructions including, but not limited to, the following examples.

#### Multi-View Subject Reference

- **Common Syntax:**

    - ***Refer to/Extract/Combine/Use**** the ****[Subject]**** from ****[Image N]**** to generate ****[Scene Description]****, maintaining consistent ****[Subject]**** features.***Multi-view Subject Reference**

#### **Multi-Image Reference** 

- **Common Syntax:**

    - ***Refer to / Extract / Combine / Follow the [Description of referenced elements] from [Image N] to generate [Scene Description], while maintaining the consistency of [Referenced Elements].***


### **Audio Reference**

> - Dreamina Seedance 2.0 supports audio references (Note: audio-only uploads are not supported).
> 
>     - You can use audio to reference specific voice characteristics or to drive lip-sync animations.
> 
>     - If your generation requires a specific sequence, please upload the files in order. You can use **"Audio 1," "Audio 2," ... "Audio n"** in your prompts for precise mapping. 
> 
>     - Simply ensure that the relationship between the generated content and the reference source is clearly defined.
> 
> 

#### Voice Reference

- **Common Syntax:**

    - ***[Character] says: "[Dialogue]," referencing the voice from [Audio N].***

#### Audio Content Reference

- **Common Syntax:**

    - ***[Intended Timing/Trigger Moment] + [Audio N]***

### **Video Reference**

> Dreamina Seedance 2.0 supports video-based referencing.
> 
> - If your workflow requires a specific sequence, please upload the files in order. You can use **"Video 1," "Video 2," ... "Video n"** in your prompts for precise mapping.
> 
> - Simply ensure that the relationship between the generated content and the reference source is clearly defined.
> 
> 

#### Motion Reference

- **Common Syntax:**

    - ***Refer to the [Motion Description] from [Video N] to generate [Scene Description], keeping the motion details consistent.***

#### Camera Motion Reference

- **Common Syntax:**

    - ***Refer to the [Camera Movement Description] from [Video N] to generate [Scene Description], keeping the cinematography consistent.***
    

#### **Visual Effects (VFX) Reference**

- **Common Syntax:**

    - **Refer to the [VFX Effects Description] from [Video N] to generate [Scene Description], keeping the special effects consistent.**


## Part 2 — Vibe Creating Method

### Camera Language Policy

Camera language should not be deleted wholesale. What genuinely needs removing is the low-value technical parameter that tells the system *how to shoot*. What needs keeping or translating is the camera *intent* that tells the audience *how to feel*.

**De-emphasise or remove by default**:

- Focal lengths, millimetre figures
- Camera-position terminology
- Camera-movement parameters
- Shot numbers
- Depth of field, aperture, exposure, shutter
- Equipment notes, A/B camera, coverage
- Pure editing instructions

When the material explicitly asks to keep parameters, honour that constraint first.

**When the fate of precise control has not been declared**:

- Do not treat technical control as something that must be kept
- Still default to the VC creative version, which generates better
- Keep whatever contributes to emotion, narrative or the viewing experience
- Remove purely technical camera control by default, or translate it into its natural visible result
- There is no need to interrupt for confirmation first; but if some technical control was de-emphasised, removed or translated, say so briefly in the output. If the user wants certain parameters, structure or beats kept, they can say so and receive a constraint-preserving version.

### Sound and Constraint Priority Rules

Dialogue, voice-over, music, sound effects, lyrics, spoken lines and any other explicitly specified sound content outrank creative optimisation. The skill may reorder them, but **must not reword them, must not substitute them, and must not delete a sound requirement the user stated explicitly**.

When rules conflict, apply this order:

1. **The user's explicit content and hard constraints**: dialogue, voice-over, music, sound effects, shot structure, parameter-retention requirements, format requirements, style limits.
2. **Creative optimisation**: within those constraints, distil the story, emotion, memory, imagery and unified experience.
3. **VC consistency**: only once the first two are satisfied, tighten the language further so the prompt is easier for the model to understand and generate.

Additional rules:

- Dialogue, voice-over, music or sound effects the user wrote out explicitly are preserved verbatim.
- When visual description and sound requirements are written together, the order may be rearranged, but the sound content itself is not altered.
- If the visual part suits VC but the sound part does not, rewrite only the visual part.
- If the whole piece depends on long-form, strict, word-level dialogue sync, do not run a VC rewrite by default.
