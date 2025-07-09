from attachments import Attachments, set_verbose
set_verbose(False)

main_prompt = """You are the and extrordinary talented electron app architect,
your task is to make a complete thorough plan for a competent coder not knowing all the
electron app by heart could follow successfully. Mention the folders and changes to do but not
need to mention specific coe, the coder will write it. please answer this que """

main_prompt = "Please carefully list the project relative path of all files I would need to modify or implement to start doing that: "

user_prompt = """
ok, I think the clipboard is not 100% working now, I would like the main hud for each them to
be a very very go interface to disply the current clipboard in formation.
Please tell my what do I have to do to make that happen.
Which file is doing what for this flow to work?
"""

user_prompt = """
I am confused about this architecture can you explain it to me
"""

Attachments("/home/maxime/Projects/metakeyaiv2/apps/metakey-desktop/src/[force:true][files:true]"
            "/home/maxime/Projects/metakeyaiv2/apps/metakey-desktop/stock-assets/[force:true][files:true]"
            "/home/maxime/Projects/metakeyaiv2/packages/config-engine/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/hotkeys-engine/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/shared-types/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/spell-engine/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/spell-book/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/system-agent/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/system-agent-engine/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/docs/normal*.md[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/docs/first*.md[force:true][files:true]"
            )\
    .to_clipboard_text(main_prompt + user_prompt)




user_prompt = """
I am confused about this architecture can you explain it to me
"""


Attachments("/home/maxime/Projects/metakeyaiv2/apps/metakey-desktop/src/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/apps/metakey-desktop/stock-assets/[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/[force:true][files:true]"
            )\
    .to_clipboard_text("I am confused about this architecture can you explain it to me")



Attachments("/home/maxime/Projects/metakeyaiv2/[force:true][files:true]")\
    .to_clipboard_text("this is how I did it in v0 or metakeyai")


Attachments("/home/maxime/Projects/metakeyaiv2/packages/system-agent[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/system-agent-engine[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/packages/clipboard-engine[force:true][files:true]",
            "/home/maxime/Projects/metakeyaiv2/docs/arch_journey_through_app.md[force:true][files:true]"
            )\
    .to_clipboard_text("Help me add the capability to know the app and the file path (and source url when applicable) as much as possible for the source and destination of ctrl-c ctrl-v")
