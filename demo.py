#!/usr/bin/env python3
"""Seed a data dir with a believable, entirely fictional person — for screenshots, demos and trying Mindbaton out.

    MINDBATON_DATA=/tmp/mb-demo python3 demo.py --password demo-pass-123
    MINDBATON_DATA=/tmp/mb-demo python3 server.py

Noor Haddad is a product designer who moved from Porto to Lisbon for a job at Kestrel Mobility. Six weeks of her chats
with ChatGPT, Claude, Gemini, Perplexity, Claude Code and Cursor go through the real ingest path (the same code the
extension and MCP use): a work project (Wayfinder), a side project (Pantry), her portfolio, half-marathon training,
preferences, a move and a job change that replace older facts, and a long Claude chat that hit its limit and was
handed to ChatGPT. Timestamps are relative to now, so it always looks current. The server never watches this machine's
Claude Code transcripts for a demo data dir, so nothing real mixes in.
"""
import os, sys, time
from datetime import datetime, timedelta

import live
import server

NOW = time.time()
HOME = os.path.expanduser("~")  # coding sessions run in ~/<project>: that is how projects pool across apps


def at(days, hour, minute=0):
    t = (datetime.now() - timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
    return min(t, NOW - 600)


# (days ago, hour, site, url, title, model, turns: user / assistant alternating, extra sync args)
CHATS = [
    (42, 20, "chatgpt.com", "https://chatgpt.com/c/6a1f-relocate", "Relocating to Lisbon", "gpt-5-5", [
        "hi! I'm Noor, a product designer. I live in Porto for now. I just accepted a job at Kestrel Mobility in Lisbon, so "
        "I'm relocating in a few weeks",
        "Congratulations on the new role! Moving from Porto to Lisbon is a big but manageable change. Want a checklist for the "
        "move — NIF address change, rental search, utilities — or help picking a neighbourhood first?",
        "neighbourhood first. I cycle to work and the office is near Cais do Sodré, what areas make sense?",
        "For a flat bike commute to Cais do Sodré: Santos, Madragoa and Estrela are close; Alcântara is flat along the river "
        "with the bike lane; Arroios is livelier but hillier. Avoid Graça or Alfama if you want to ride every day.",
        "I have a cat named Miso. are pet-friendly rentals hard to find there?",
        "They're less common but not rare — filter for 'aceita animais' on Idealista and mention Miso up front. Landlords in "
        "Alcântara and Campo de Ourique tend to be more flexible than in the centre."]),
    (33, 10, "claude.ai", "https://claude.ai/chat/2b7e-wayfinder", "Wayfinder trip planner critique", "claude-opus-5", [
        "I'm working on Wayfinder, a redesign of the trip planner in the Kestrel app. Riders plan metro + bus + bike trips in one flow",
        "Nice scope. The hard part of multimodal planners is the result list: riders compare time, transfers and walking at a "
        "glance. I'd lead with arrival time and a compact leg strip (metro → walk → bus) and push fares into details.",
        "our design system uses Figma variables for color tokens. how should I structure light and dark modes?",
        "Use two collections: primitives (raw palette, no modes) and semantic tokens (surface, text/primary, line/accent) with "
        "Light and Dark modes that alias primitives. Components only ever reference semantic tokens.",
        "the contrast of our secondary text fails WCAG AA on the map overlay, what can I do about it?",
        "Three options: darken text/secondary on overlay surfaces only (a scoped token), add a subtle scrim behind the card, or "
        "raise the font weight to 500 at 14px. The scoped token is the least disruptive.",
        "I prefer fewer modes and bigger touch targets over a dense UI, riders use this one-handed on a moving bus",
        "Then 48px minimum targets, one primary action per card, and no hover-only affordances. Dense tables can live in a "
        "'details' sheet for the few who want them."]),
    (30, 7, "www.perplexity.ai", "https://www.perplexity.ai/search/lisbon-half-3kd", "Lisbon half marathon", "sonar-pro", [
        "when is the Lisbon half marathon and how hard is the course?",
        "The Lisbon Half Marathon runs in March. The classic course crosses the 25 de Abril bridge early and is mostly flat "
        "along the river afterwards — fast, but the bridge climb and wind can bite.",
        "I want to run a half marathon under 1:55 by March",
        "Sub-1:55 is about 5:27/km. With ~20 weeks, three runs a week — one long, one tempo, one easy — gets most runners there.",
        "I use Strava to track every run. how do I stop knee pain after 12 km?",
        "Knee pain past a set distance often points to load or form: add strength work for hips and glutes twice a week, raise "
        "long runs by no more than 10% a week, and see a physio if it persists."]),
    (28, 21, "gemini.google.com", "https://gemini.google.com/app/5c0d-portuguese", "Portuguese café phrases", "gemini-3-pro", [
        "I'm learning European Portuguese. give me 10 phrases for ordering at a café",
        "Queria um galão, por favor · Um café (an espresso) · Uma meia de leite · Posso pagar com cartão? · Tem leite de aveia? "
        "· Para levar · Para comer aqui · A conta, se faz favor · Obrigada · Até amanhã!",
        "I'm vegetarian. what pastries are there besides pastel de nata?",
        "Try bola de Berlim, queijada de Sintra, travesseiro, pão de Deus and broa. Most are vegetarian; ask 'tem banha?' "
        "(does it have lard?) for the older recipes."]),
    (24, 14, "claude-code", None, "Scaffold Pantry with Next.js and Supabase", "claude-sonnet-5", [
        "scaffold a Next.js app with Tailwind and Supabase auth for Pantry, a meal planner for flatmates",
        "Done. Created the app with the App Router, Tailwind, and Supabase auth (magic link). Added `lib/supabase/server.ts` "
        "and a `households` + `recipes` schema in `supabase/migrations/0001_init.sql`.",
        "use TypeScript strict mode, I prefer server actions over API routes",
        "Enabled `strict` in tsconfig and moved recipe creation to a server action in `app/recipes/actions.ts`; removed the "
        "`/api/recipes` route.",
        "the Supabase row level security policy blocks inserts into recipes, fix it",
        "The insert policy checked `auth.uid() = owner_id` but the action never set `owner_id`. Now the action sets it and the "
        "policy is:\n```sql\ncreate policy \"members insert\" on recipes for insert\n  with check (household_id in (select household_id "
        "from members where user_id = auth.uid()));\n```"], {"cwd": HOME + "/pantry", "key": "claude-code/3f2a9c1e-pantry"}),
    (20, 22, "cursor", None, "Pantry shopping list by aisle", "claude-sonnet-5", [
        "add a shopping list page to Pantry that groups ingredients by supermarket aisle",
        "Added `app/list/page.tsx` with a server component that groups missing ingredients by `aisle` (produce, dairy, dry "
        "goods, frozen) and a checkbox per item that syncs through Supabase realtime.",
        "I use pnpm, not npm — update the scripts and the README",
        "Switched the lockfile to pnpm, updated `package.json` scripts and the README setup steps."], {"cwd": HOME + "/pantry", "key": "mcp/cursor/pantry-shopping-list"}),
    (18, 19, "chatgpt.com", "https://chatgpt.com/c/7d20-portfolio", "Portfolio site in Astro", "gpt-5-5", [
        "I'm rebuilding my portfolio site with Astro, it's currently hosted on Netlify",
        "Good pick for a portfolio: Astro ships zero JS by default. Use content collections for case studies and the Image "
        "component for your mockups.",
        "how do I add case study pages from markdown with a reading time?",
        "Define a `caseStudies` collection with a zod schema, then compute reading time in a remark plugin that writes "
        "`minutesRead` into the frontmatter; render it on `[slug].astro`.",
        "I switched from Notion to Obsidian. can Astro read case studies straight from the vault?",
        "Yes — point the collection's loader at a folder inside the vault, and convert [[wiki links]] with a remark plugin."]),
]
LIMITED = (12, 9, "claude.ai", "https://claude.ai/chat/9e41-pantry-onboarding", "Pantry onboarding flow", "claude-opus-5", [
    "I'm building Pantry, a meal planner for flatmates, as a side project. I'm designing its onboarding now — goal: a new "
    "flatmate joins the household and sees the shared pantry in under a minute",
    "Great north star. Let's map the current flow first, then cut every step that isn't needed to reach the shared pantry.",
    "current flow: sign up, create household, name it, invite, scan a receipt. drop-off is 60% at the invite step. the app is "
    "Next.js and Supabase with households, members and recipes tables, if that matters for the join flow",
    "The invite step asks the existing member to do work for someone else — that's why it drops. Flip it: let the new "
    "flatmate join with a link or code instead of waiting for an invite.",
    "what if the invite is a QR code on the fridge?",
    "Love it — physical, shared, and it matches how flatmates actually coordinate. The QR opens the join screen with the "
    "household pre-filled. Print it from settings as a small fridge card.",
    "I prefer progressive disclosure over long forms",
    "Then the join screen asks only for a name. Dietary preferences, allergies and notification settings come later, "
    "when they first matter.",
    "let's decide: skip the household name step and generate one from the street name",
    "Decided: household name = street name + door (\"Rua da Esperança 12\"), editable later. That removes one screen.",
    "for the empty state, show three starter recipes based on what's usually in a Portuguese pantry",
    "Starter set: bacalhau à brás (or a chickpea version for vegetarians), caldo verde, and arroz de tomate — all built "
    "from rice, potatoes, onions, garlic, olive oil and canned tomatoes.",
    "write the microcopy for the join screen. friendly, not cute",
    "Title: \"Join Rua da Esperança 12\" · Body: \"See what's in the pantry and what's for dinner.\" · Button: \"Join "
    "household\" · Secondary: \"Not your flat? Scan again\"",
    "the receipt scanner should be optional, put it after the first recipe",
    "Agreed — scanning is a power move, not an entry fee. Offer it on the recipe screen: \"Missing something? Scan your "
    "last receipt to update the pantry.\"",
    "what about accessibility for the QR flow? screen readers can't scan a fridge card",
    "Print a short 6-letter code under the QR and offer \"Enter a code\" on the join screen; the code is read aloud by "
    "VoiceOver and TalkBack and works on a laptop too.",
    "still open: how do we handle one person in two households? my friend Ana splits her week between two flats"],
    "This conversation reached its maximum length. Start a new chat to continue.")
LATER = [
    (8, 11, "gemini.google.com", "https://gemini.google.com/app/8a3e-tokens", "Figma variables to Tailwind", "gemini-3-pro", [
        "how can I export Figma variables to a Tailwind config automatically?",
        "Use the Figma REST API's variables endpoint in a small script that writes `tokens.json`, then map semantic tokens "
        "to CSS variables in `tailwind.config.ts` so dark mode is a class switch.",
        "we use Tokens Studio at Kestrel but I'd rather not add another plugin to Pantry",
        "Then keep the script: one `pnpm tokens` command, run in CI, no plugin to maintain."]),
    (6, 13, "www.perplexity.ai", "https://www.perplexity.ai/search/standing-desk-9xa", "Standing desk in Lisbon", "sonar-pro", [
        "where can I buy a standing desk in Lisbon with delivery? budget under 400 euros",
        "IKEA Alfragide (Trotten, Bekant), Worten and Flexispot's EU store all deliver in Lisbon; Flexispot E5 is often on "
        "sale under €350."]),
    (4, 20, "claude-code", None, "Astro case study collection", "claude-sonnet-5", [
        "add an Astro content collection for case studies with a reading time",
        "Added `src/content/config.ts` with a `caseStudies` collection and a remark plugin that sets `minutesRead`; the "
        "case study layout shows it under the title.",
        "move the deploy from Netlify to Cloudflare Pages",
        "Removed `netlify.toml`, added `wrangler.toml` and a GitHub Action that builds with pnpm and deploys to Cloudflare Pages."],
        {"cwd": HOME + "/portfolio", "key": "claude-code/8b1d44e0-portfolio"}),
    (2, 23, "cursor", None, "Pantry recipe import", "gpt-5-codex", [
        "write a parser for Pantry that imports recipes from a URL using the schema.org Recipe JSON-LD",
        "Added `lib/import-recipe.ts`: fetches the page, finds `application/ld+json` blocks, picks the `Recipe` node and maps "
        "ingredients and steps; tests cover three real-world shapes."], {"cwd": HOME + "/pantry", "key": "mcp/cursor/pantry-recipe-import"}),
    (1, 16, "claude.ai", "https://claude.ai/chat/c3f8-usability", "Wayfinder usability test plan", "claude-opus-5", [
        "Next week I'm testing Wayfinder with five commuters, help me write the tasks",
        "Five tasks, each a real trip: 1) home to work by 9:00, 2) a trip with the fewest transfers, 3) a bike + metro combo, "
        "4) change the arrival time, 5) save a trip for tomorrow. Measure time on task and where they hesitate.",
        "participants are commuters who ride the metro and buses in Lisbon every day",
        "Then use their own commutes for task 1 and a trip they've never taken for task 3 — familiar and unfamiliar routes "
        "reveal different problems."]),
]
CAPTURES = [  # said in a chat the extension saved without Live mode: (days ago, hour, site, chat title, text)
    (45, 18, "chatgpt.com", "Portfolio feedback", "I work at Fernhill Studio in Porto as a product designer"),
    (44, 9, "claude.ai", "Design tools", "I design everything in Figma"),
    (36, 9, "chatgpt.com", "New job", "I left Fernhill Studio, now I work at Kestrel Mobility as a senior product designer"),
    (26, 20, "gemini.google.com", "Moving", "I moved to Lisbon last weekend, the flat is in Alcântara"),
    (25, 8, "claude.ai", "Desk setup", "I use a MacBook Air M3 with an external 27 inch monitor"),
    (15, 15, "chatgpt.com", "Coffee", "I love specialty coffee, usually an oat flat white"),
    (14, 22, "www.perplexity.ai", "Obsidian sync", "is Obsidian Sync end-to-end encrypted?"),
    (9, 21, "gemini.google.com", "Settings", "I prefer dark mode in every app"),
    (5, 19, "gemini.google.com", "Design heroes", "my favourite designer is Dieter Rams"),
    (3, 10, "chatgpt.com", "Tools", "I prefer Linear over Jira for tracking design work"),
    (3, 12, "chatgpt.com", "Hosting", "I switched from Netlify to Cloudflare Pages"),
    (0, 0, "claude.ai", "Daily tools", "I use Raycast and the Arc browser every day"),
]
REMEMBERED = [  # saved by agents over MCP: (days ago, hour, ai, model, fact)
    (20, 23, "Cursor", "claude-sonnet-5", "The user prefers pnpm over npm"),
    (19, 10, "Cursor", "claude-sonnet-5", "The user deploys Pantry on Vercel"),
    (4, 21, "Claude Code", "claude-sonnet-5", "The user's portfolio is built with Astro and deployed on Cloudflare Pages"),
]


def turns_of(texts, start, model):
    return [{"role": "user" if i % 2 == 0 else "assistant", "text": t, "ts": start + i * 170,
             "model": None if i % 2 == 0 else model} for i, t in enumerate(texts)]


def sync(g, chat, limit=None):
    days, hour, site, url, title, model, texts, *extra = chat
    turns = turns_of(texts, at(days, hour), model)
    return live.sync(g, url, site, title, turns, limit=limit, model=model, ts=turns[-1]["ts"], **(extra[0] if extra else {}))


def main():
    if os.path.exists(server.DB):
        sys.exit(f"{server.DB} already exists — demo.py only seeds a fresh data dir (point MINDBATON_DATA at an empty folder)")
    os.makedirs(server.DATA, mode=0o700, exist_ok=True)
    g = server.Graph()
    g.meta("demo", "1")  # the server won't watch this machine's Claude Code transcripts for this data dir
    for days, hour, site, chat, text in CAPTURES:
        g.ingest(text, site, chat, None, at(days, hour) if days else NOW - 1500)
    for chat in CHATS:
        sync(g, chat)
    for days, hour, who, model, fact in REMEMBERED:
        g.ingest(fact, "agent", ts=at(days, hour), meta={"ai": who, "model": model, "model_src": "self"})
    old = sync(g, LIMITED[:7], limit=LIMITED[7])
    pack = live.make_handoff(g, str(old["id"]), 1500)["text"]  # the baton: Claude's full chat continues in ChatGPT
    sync(g, (10, 8, "chatgpt.com", "https://chatgpt.com/c/b51c-pantry-continued", "Pantry onboarding, continued", "gpt-5-5", [
        pack + "\n\nPicking this up here — can you help with the two-households question?",
        "Sure. Model membership as person ↔ household (many-to-many) instead of a single household per user. The app opens the "
        "household you used last, with a switcher in the header; notifications are per household.",
        "and what does Pantry show when she's in the other flat that week? the Supabase members table has one row per household",
        "Only that household's pantry. Shared staples don't sync across flats — that would surprise both sets of flatmates.",
        "ok, decided: many-to-many membership, last-used household opens first, no cross-household sync"]))
    for chat in LATER:
        sync(g, chat)
    g.rebuild()  # derive everything once more in time order, exactly as a restart after an upgrade would
    if "--password" in sys.argv:
        pw = sys.argv[sys.argv.index("--password") + 1] if sys.argv.index("--password") + 1 < len(sys.argv) else ""
        if len(pw) < 8:
            sys.exit("--password needs at least 8 characters")
        server.set_password(g.db, server.hash_password(pw))
    stats = g.graph()["stats"]
    print(f"Seeded {server.DB}: {stats['captures']} captures, {stats['memories']} memories, {stats['entities']} things, "
          f"{stats['chats']} chats, {len(g.topics)} topics" + ("" if "--password" in sys.argv else " (no owner yet: first visit sets the password)"))


if __name__ == "__main__":
    main()
