from attachments.dspy import Attachments
import dspy

# Test with attachments
print("=== Testing with attachments ===")
lm = dspy.LM(model="gemini/gemini-2.0-flash")
dspy.configure(lm=lm)

sign = dspy.Signature("picture -> weight", instructions="extract the weight value from the image")
weight_extractor = dspy.ChainOfThought(sign)

image_paths = [
    "/home/maxime/whispers/meat_labels/Nov2024Bouwman/IMG_2797.HEIC",
    "/home/maxime/Pictures/Screenshots/Screenshot from 2025-06-13 07-06-22.png"
]

dsl_variants = [
    ("default", "{path}"),
    ("text:false", "{path}[text:false]"),
    ("images:false", "{path}[images:false]"),
    ("text:false,images:false", "{path}[text:false][images:false]")
]

for path in image_paths:
    print(f"\n=== Testing {path} with dspy.Image ===")
    img = dspy.Image.from_file(path)
    result = weight_extractor(picture=img)
    print("dspy.Image result:")
    print(result)

    for label, dsl in dsl_variants:
        dsl_path = dsl.format(path=path)
        print(f"\n=== Testing {dsl_path} with Attachments ({label}) ===")
        att = Attachments(dsl_path)
        result = weight_extractor(picture=att)
        print(f"Attachments result ({label}):")
        print(result) 