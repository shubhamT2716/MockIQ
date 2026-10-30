"""Browser test for hands-free voice: fakes the microphone and speaker, then talks to the app.

    pip install playwright && python -m playwright install chromium
    python -m scripts.e2e_voice

Starts its own server with the fake LLM and a throwaway database.
"""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.async_api import async_playwright


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}/"
FAKES = """
window.__spoken = []; window.__listening = false; window.__active = null;
class FakeSR { start(){ window.__active = this; window.__listening = true; }
               stop(){ window.__listening = false; setTimeout(() => this.onend && this.onend(), 10); } }
window.webkitSpeechRecognition = FakeSR; window.SpeechRecognition = FakeSR;
window.__say = (text) => { const r = window.__active; if (!r || !window.__listening) return false;
  r.onresult({ resultIndex: 0, results: [{ 0: { transcript: text }, isFinal: true, length: 1 }] }); return true; };
window.__interim = (text) => { const r = window.__active;
  r.onresult({ resultIndex: 0, results: [{ 0: { transcript: text }, isFinal: false, length: 1 }] }); };
const synth = { getVoices: () => [], cancel(){}, onvoiceschanged: null,
  speak(u){ window.__spoken.push(u.text); setTimeout(() => u.onend && u.onend(), 15); } };
Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
window.SpeechSynthesisUtterance = class { constructor(t){ this.text = t; } };
"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await (await b.new_context()).new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.add_init_script(FAKES)
        async def listening(): await pg.wait_for_function("window.__listening === true", timeout=10000)
        async def say(t):
            await listening(); assert await pg.evaluate("t => window.__say(t)", t), f"not listening for: {t}"
        async def candidate_bubbles(): return await pg.locator("#transcript li.candidate p").all_inner_texts()
        async def wait_bubbles(n): await pg.wait_for_function(f"document.querySelectorAll('#transcript li.candidate').length >= {n}", timeout=15000)

        await pg.goto(BASE + "#/signup"); await pg.wait_for_selector("#auth:not([hidden])")
        await pg.fill("#authName", "Asha"); await pg.fill("#authEmail", f"voice{int(time.time())}@x.com"); await pg.fill("#authPassword", "correct-horse-1")
        await pg.click("#authSubmit"); await pg.wait_for_selector(".empty")
        await pg.goto(BASE + "#/new"); await pg.wait_for_selector("#roundChoices label")
        boxes = await pg.query_selector_all('input[name="round"]')
        for bx in boxes[1:]: await bx.uncheck()
        await pg.click("#startBtn"); await pg.wait_for_selector("#transcript li.interviewer")
        await pg.select_option("#silenceSel", "2000")
        await listening()
        print("1. auto-listened after the opening question:", True)

        n_spoken = await pg.evaluate("window.__spoken.length")
        await say("Can you repeat the question?")
        q = await pg.locator("#transcript li.interviewer p").last.inner_text()
        # wait until everything said since the command equals the question, word for word
        await pg.wait_for_function("([n, q]) => window.__spoken.slice(n).join(' ') === q", arg=[n_spoken, q], timeout=5000)
        assert await pg.input_value("#answer") == ""
        print("2. repeat ok")

        await say("I would run BFS from every unvisited land cell and count the components")
        await pg.wait_for_selector("#autosend:not([hidden])", timeout=4000)
        print("3. countdown shown:", await pg.inner_text("#autosendText"))
        await wait_bubbles(1)
        print("   auto-sent after pause:", (await candidate_bubbles())[-1][:40])

        await say("I'd skip this question of locking and use optimistic concurrency instead")
        await say("That's my answer")
        await wait_bubbles(2)
        last = (await candidate_bubbles())[-1]
        assert "skip this question of locking" in last and not last.lower().endswith("answer")
        print("4. no false trigger, explicit submit ok")

        await say("First I would hash the keys")
        await say("Give me a minute")
        await asyncio.sleep(5)
        held = len(await candidate_bubbles()) == 2
        await say("and then keep a heap of size k")
        await wait_bubbles(3)
        assert held and (await candidate_bubbles())[-1].startswith("First I would hash the keys and then")
        print("5. give me a minute ok")

        await say("Can I skip this one?")
        await wait_bubbles(4)
        assert (await candidate_bubbles())[-1] == "(Skipped this question)"
        print("6. skip ok")

        await say("speak slower")
        await pg.wait_for_function("JSON.parse(localStorage.getItem('mockiq.voice')||'{}').rate < 1")
        print("7. speak slower -> rate", await pg.evaluate("JSON.parse(localStorage.getItem('mockiq.voice')).rate"))

        await say("Some words I want to remove")
        await say("clear my answer")
        await asyncio.sleep(0.3)
        assert await pg.input_value("#answer") == ""
        print("8. clear ok")

        await say("End the interview")
        await pg.wait_for_function("window.__spoken.join(' ').includes('Say yes to end')")
        await say("no")
        await pg.wait_for_function("window.__spoken.join(' ').includes(\"let's continue\")")
        assert "#/interview/" in pg.url
        print("9. end + no ok")
        await say("End the interview")
        await asyncio.sleep(0.4)
        await say("yes")
        await pg.wait_for_selector(".verdict", timeout=20000)
        assert "#/report/" in pg.url
        print("10. end + yes ok")
        txt = await pg.inner_text("#reportBody")
        assert "Skipped" in txt
        assert not errs, errs
        print("All voice checks passed.")
        await b.close()


def run():
    db = os.path.join(tempfile.mkdtemp(), "e2e.db")
    env = {**os.environ, "LLM_PROVIDER": "fake", "DATABASE_URL": f"sqlite:///{db}"}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--port", str(PORT)],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "api/health", timeout=1); break
            except OSError:
                time.sleep(0.2)
        asyncio.run(main())
    finally:
        srv.terminate()


if __name__ == "__main__":
    run()
