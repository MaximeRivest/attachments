from attachments.dspy import Attachment
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

for path in image_paths:
    print(f"\n=== Testing {path} with dspy.Image ===")
    img = dspy.Image.from_file(path)
    result = weight_extractor(picture=img)
    print("dspy.Image result:")
    print(result)

    print(f"\n=== Testing {path} with attachments.dspy.Attachment ===")
    att = Attachment.from_files(path)
    result_att = weight_extractor(picture=att)
    print("attachments.dspy.Attachment result:")
    print(result_att) 