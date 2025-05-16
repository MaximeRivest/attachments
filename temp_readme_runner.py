from attachments import Attachments

PDF_URL = "https://raw.githubusercontent.com/MaximeRivest/attachments/main/examples/sample.pdf"
PPTX_URL = "https://raw.githubusercontent.com/MaximeRivest/attachments/main/examples/sample.pptx"
WIKIMEDIA_JPG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/BremenBotanikaZen.jpg/1280px-BremenBotanikaZen.jpg"

a = Attachments(PDF_URL, PPTX_URL, WIKIMEDIA_JPG_URL, verbose=False)
print(a) 