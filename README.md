# Qwen2.5-VL Quick Test README.md
This repository contains a minimal setup for testing the **Qwen/Qwen2.5-VL-3B-Instruct** model — a multimodal vision-language model capable of processing **text + image** (and optionally video) inputs using 🤗 Transformers.

The goal of this test is to explore how well Qwen2.5-VL performs on **practical tasks** such as:

- Extracting structured information from screenshots and documents
- Describing images
- Classifying visual attributes (e.g., age group)
- Parsing financial statements
---
## What is Being Tested?
I tested the model on five main scenarios:
1. **Twitter profile info extraction** from a screenshot
2. **Receipt data extraction** (business name, date, total)
3. **Age classification** from a person’s image
4. **Image description** (detailed captions)
5. **Bank statement data extraction** (transactions, money in/out)

These tasks were chosen to see how well the model handles:
- Text extraction from images (pseudo-OCR)
- Understanding and following structured prompts
- Interpreting image context for descriptions and classification
---
## How It Works
The workflow is:
1. Prepare the prompt → a messages list containing both the image(s) and the task description as text.
2. Process inputs → using Qwen’s AutoProcessor and process_vision_info to format images for the model.
3. Run inference → model.generate() to get model outputs.
4. Post-process → trim prompt tokens and decode the generated IDs into text or JSON.
---
## Test Prompts
Here are the messages definitions for each task:

### 1) Twitter account info extraction
```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": "images/twitter_profile.jpg"},
            {"type": "text", "text": (
                "From this screenshot, return ONLY valid JSON with keys: "
                "username, followers, following, posts. "
                "Rules: numbers as integers (no commas), if missing use \"na\"."
            )},
        ],
    }
]

```

2) Receipt data extraction
```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": "images/receipt.jpg"},
            {"type": "text", "text": (
                "From this receipt image, extract the following fields and return valid JSON only:\n"
                "- place_name → the name of the business at the top.\n"
                "- date → format DD/MM/YYYY.\n"
                "- total → numbers only (no currency symbol).\n"
                "If missing, return \"na\". Numbers as int/float. Output ONLY valid JSON."
            )},
        ],
    }
]

```

3) Age classification
```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": "images/dogAndMan.jpg"},
            {"type": "text", "text": (
                "Look at the person in this image and classify their age group as one of: "
                "child, teenager, young adult, adult, senior. Return only the category."
            )},
        ],
    }
]

```

4) Image description
```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": "images/dogAndMan.jpg"},
            {"type": "text", "text": "Describe in detail what is shown in the image."},
        ],
    }
]

```

5) Bank statement data extraction
```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": "images/bankStatement.jpg"},
            {"type": "text", "text": (
                "From this bank statement image, extract all transactions as JSON with the keys: "
                "date, description, money_in, money_out, balance. Numbers as float/int without currency symbols."
            )},
        ],
    }
]

```
---
## Requirements
My test environment:
- Python 3.10
- PyTorch (GPU, CUDA 12.8)
- transformers==4.56.0.dev
- accelerate, huggingface_hub
- pillow, opencv-python (optional for video)

Install:
```bash
pip install transformers accelerate huggingface_hub pillow opencv-python
```

---
## Results from My Testing
- Not an OCR model → While Qwen2.5-VL can read text from images, it is not a dedicated OCR model.
- Twitter handles with underscores → Often fails to detect underscores (@Ziad_tamim_ read as @ZiadTamim).
- Numbers → Very good at reading numbers such as followers, amounts, and counts.
- Receipts & bank statements → Reads values and dates accurately most of the time (≈ 90% success rate in my trials).
- Descriptions → Excellent at describing scenes and identifying objects.
- General rule → For best accuracy, use clear, high-quality images and explicit instructions in the text prompt.


