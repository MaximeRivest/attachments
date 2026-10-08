
| Command | Type | Default | Allowable Values | Used In |
|---|---|---|---|---|
| `characters` | `int` | `1000` | — | `splitter.characters` |
| `columns` | `int` | `10` | — | `splitter.columns` |
| `custom`<br><small><em>separator.</em></small> | `string` | `---` | `separator` | `splitter.custom` |
| `dirs_only_with_files` | `string` | `true` | `true`, `false` | `loader.directory_to_structure` |
| `files`<br><small><em>false</em></small> | — | — | `true`, `false` | `loader.directory_to_structure`<br>`loader.git_repo_to_structure` |
| `force` | `string` | `false` | `true`, `false` | `loader.directory_to_structure`<br>`loader.git_repo_to_structure` |
| `format`<br><small><em>commands.</em></small> | `string` | `markdown` | `plain`, `text`, `txt`, ... (10 total) | `_get_smart_text_presenter`<br>`loader.directory_to_structure`<br>`loader.git_repo_to_structure`<br>`processor.csv_to_llm`<br>`processor.docx_to_llm`<br>`processor.eps_to_llm`<br>`processor.excel_to_llm`<br>`processor.pdf_to_llm`<br>`processor.pptx_to_llm`<br>`processor.svg_to_llm`<br>`processor.webpage_to_llm` |
| `fullpage` | `string` | `true` | `true`, `false` | `presenter.images` |
| `glob`<br><small><em>pattern structure and file list.     ...</em></small> | `string` | — | — | `loader.directory_to_structure`<br>`loader.git_repo_to_structure` |
| `head`<br><small><em>true</em></small> | `string` | `false` | `true`, `false` | `processor.csv_to_llm` |
| `ignore` | `string` | `standard` | — | `loader.directory_to_structure`<br>`loader.git_repo_to_structure` |
| `images`<br><small><em>true</em></small> | `string` | `true` | `true`, `false` | `processor.docx_to_llm`<br>`processor.excel_to_llm`<br>`processor.pdf_to_llm`<br>`processor.pptx_to_llm`<br>`processor.webpage_to_llm` |
| `lang`<br><small><em>uage for OCR using the `lang` command</em></small> | `string` | `eng` | `ara]`` | `presenter.ocr` |
| `limit`<br><small><em>pandas DataFrame rows.</em></small> | — | — | — | `modifier.limit` |
| `lines` | `int` | `50` | — | `splitter.lines` |
| `max_files` | `int` | `1000` | — | `loader.directory_to_structure`<br>`loader.git_repo_to_structure` |
| `mode` | — | — | — | `loader.directory_to_structure`<br>`loader.git_repo_to_structure` |
| `ocr`<br><small><em>auto</em></small> | `string` | `auto` | `auto`, `true`, `false` | `processor.pdf_to_llm` |
| `prompt` | `string` | — | — | `adapter.agno`<br>`adapter.claude`<br>`adapter.to_clipboard_text` |
| `recursive` | `string` | `true` | `true`, `false` | `loader.directory_to_structure` |
| `resize` | — | — | — | `presenter.images`<br>`presenter.images`<br>`presenter.images` |
| `resize_images` | — | — | — | `presenter.images`<br>`presenter.images`<br>`presenter.images`<br>`presenter.images`<br>`presenter.images`<br>`presenter.images`<br>`refiner.resize_images` |
| `rotate` | — | — | `degrees` | `modifier.rotate` |
| `rows` | `int` | `100` | — | `splitter.rows` |
| `select`<br><small><em>columns from pandas DataFrame.</em></small> | — | — | — | `modifier.select`<br>`presenter.images`<br>`processor.webpage_to_llm` |
| `split`<br><small><em>paragraphs</em></small> | — | — | `paragraphs`, `sentences`, `tokens`, ... (6 total) | `processor.webpage_to_llm` |
| `summary`<br><small><em>true</em></small> | `string` | `false` | `true`, `false` | `processor.csv_to_llm` |
| `tile`<br><small><em>2x2 grid</em></small> | `string` | `2x2` | `2x2` | `refiner.tile_images` |
| `tokens` | `int` | `500` | — | `splitter.tokens` |
| `truncate`<br><small><em>text content to specified character l...</em></small> | `int` | `1000` | `text content` | `refiner.truncate` |
| `viewport` | `string` | `1280x720` | — | `presenter.images` |
| `wait` | `int` | `200` | — | `presenter.images` |