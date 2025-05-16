from PIL import Image

# Create a 1x1 red PNG image
img_png = Image.new('RGB', (1, 1), color = 'red')
img_png.save('sample.png', 'PNG')

# Create a 1x1 blue JPEG image
img_jpg = Image.new('RGB', (1, 1), color = 'blue')
img_jpg.save('sample.jpg', 'JPEG')

print("sample.png and sample.jpg created in tests/test_data/") 