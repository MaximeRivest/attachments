import dspy

lm = dspy.LM(model="gemini/gemini-2.0-flash")
dspy.configure(lm=lm)

sign = dspy.Signature("picture -> weight", instructions="extract the weight value from the image")
weight_extractor = dspy.ChainOfThought(sign)

image_path = "/home/maxime/Pictures/Screenshots/Screenshot from 2025-06-13 07-06-22.png"

# 1. Only image (like dspy.Image)
with open(image_path, "rb") as f:
    import base64
    img_bytes = f.read()
    img_data_url = f"data:image/png;base64,{base64.b64encode(img_bytes).decode('utf-8')}"

image_only = {"images": [img_data_url]}
print("\n--- Only image dict sent to dspy ---\n", image_only)
result_img = weight_extractor(picture=image_only)
print("Result (image only):", result_img)

# 2. Image + text (like Attachments)
text_and_image = {
    "text": "This is a test file info. There is no weight here.",
    "images": [img_data_url]
}
print("\n--- Image + text dict sent to dspy ---\n", text_and_image)
result_both = weight_extractor(picture=text_and_image)
print("Result (image + text):", result_both) 