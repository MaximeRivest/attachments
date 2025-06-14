#%%
from attachments.dspy import Attachments
import dspy
from attachments.data import get_sample_path

# Option 1: Use included sample files (works offline)
test_image_path = get_sample_path("Figure_1.png")

lm = dspy.LM(model="openai/gpt-4.1-mini")
dspy.configure(lm=lm)

att = Attachments(test_image_path)
assert att.images is not None, "Images should be non-empty"
assert len(att.images) == 1, "Should have exactly one image"
assert att.images[0] is not None, "Image should be non-empty"
assert att.images[0].startswith("data:image/png;base64,"), "Image should be a data URL"

assert len(att.text) > 0, "Text should be non-empty"

test_program = dspy.Predict("picture -> max_value_on_y_axis: int, names_on_x_axis: list[str]")
dspy_resp = test_program(picture=att)
print(dspy_resp)
assert dspy_resp.max_value_on_y_axis is not None, "Max value should be non-empty"
assert isinstance(dspy_resp.max_value_on_y_axis, int), "Max value should be an integer"
assert dspy_resp.names_on_x_axis is not None, "Names should be non-empty"
assert isinstance(dspy_resp.names_on_x_axis, list), "Names should be a list"
assert len(dspy_resp.names_on_x_axis) > 0, "Names list should be non-empty"

# %%
from attachments.dspy import Attachments  # This now automatically registers the type!
from attachments import Attachment
import dspy

# Test that automatic type registration worked
import typing
assert hasattr(typing, 'Attachments'), "Attachments should be automatically registered in typing module"
assert typing.Attachments is Attachments, "typing.Attachments should point to our Attachments class"
print("✅ Automatic type registration successful!")

lm = dspy.LM(model="gemini/gemini-2.0-flash-lite")
dspy.configure(lm = lm)

image_paths = [
    "/home/maxime/whispers/meat_labels/Nov2024Bouwman/IMG_2797.HEIC",
    "/home/maxime/Pictures/Screenshots/Screenshot from 2025-06-13 07-06-22.png"
]

# Alternative approach: Use class-based signature (more reliable)
class WeightExtractorSignature(dspy.Signature):
    """Extract the weight value from the image"""
    picture: Attachments = dspy.InputField()
    weight: float = dspy.OutputField()

weight_extractor = dspy.ChainOfThought(WeightExtractorSignature)
att = Attachments(image_paths[1])
result = weight_extractor(picture=att)
print(result)

assert result.weight == 0.29, "Weight should be 0.29"

# %%
# String-based approach - should now work automatically!

sign = dspy.Signature("picture: Attachments -> weight: float", instructions = "extract the weight value from the image")
weight_extractor = dspy.ChainOfThought(sign)
att = Attachments(image_paths[1])
result = weight_extractor(picture=att)
print(result)

assert result.weight == 0.29, "Weight should be 0.29"

print("🎉 Both class-based and string-based DSPy signatures work perfectly!")

# %%
from attachments import Attachments  # This now automatically registers the type!
import dspy

sign = dspy.Signature("picture -> weight: float", instructions = "extract the weight value from the image")
weight_extractor = dspy.ChainOfThought(sign)
att = Attachments(image_paths[1])
result = weight_extractor(picture=att.dspy())
print(result)

assert result.weight == 0.29, "Weight should be 0.29"

print("🎉 Both class-based and string-based DSPy signatures work perfectly!")

# %%
