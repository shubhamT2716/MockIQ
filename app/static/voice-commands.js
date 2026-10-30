/* Spoken command recognition for hands-free interviews.
   Commands only count when spoken on their own (a short segment), so phrases
   inside a real answer ("...I'd skip this question of locking...") never trigger. */
(function (root) {
  "use strict";
  const MAX_COMMAND_WORDS = 9;
  const LEAD = /^(?:(?:okay|ok|so|um+|uh+|hmm+|sorry|hey|actually|yeah|alright|well|excuse me)\s+)+/;
  const TRAIL = /(?:\s+(?:please|now|thanks|thank you|for me|sir|ma'am|maam))+$/;

  function norm(s) {
    return String(s || "").toLowerCase().replace(/[’‘`]/g, "'").replace(/[^a-z0-9' ]+/g, " ").replace(/\s+/g, " ").trim();
  }
  function core(s) {
    let n = norm(s), prev;
    do { prev = n; n = n.replace(LEAD, "").replace(TRAIL, "").replace(/^please\s+/, "").trim(); } while (n !== prev);
    return n;
  }
  const words = (s) => (norm(s) ? norm(s).split(" ").length : 0);

  const COMMANDS = [
    { type: "repeat", res: [
      /^(?:can|could|would|will) you (?:repeat|say) (?:that|the question|it|the last question)(?: again)?$/,
      /^repeat(?: that| the question| it| the last question)?(?: again)?$/,
      /^(?:say that again|come again|pardon(?: me)?|what was the question(?: again)?)$/,
      /^i (?:didn't|did not|couldn't|could not) (?:get|catch|hear|understand) (?:that|the question|you)$/,
    ] },
    { type: "think", res: [
      /^(?:give me|can i (?:have|get|take)|could i (?:have|get|take)|i need|let me take) (?:a|one|a few) (?:minute|moment|second|sec|seconds|minutes)(?: to think)?$/,
      /^let me think(?: about (?:it|this|that))?(?: for a (?:minute|moment|second|sec))?$/,
      /^(?:hold on|one (?:minute|moment|second|sec)|just a (?:minute|moment|second|sec))$/,
    ] },
    { type: "skip", res: [
      /^(?:can|could|may) (?:i|we) (?:please )?skip (?:this|that|it)(?: one| question)?$/,
      /^skip (?:this|that|it)(?: one| question)?$/,
      /^i(?:'d| would) like to skip (?:this|that|it)(?: one| question)?$/,
      /^(?:let's|lets) skip (?:this|that|it)(?: one| question)?$/,
    ] },
    // Ambiguous phrases only count as "skip" before the candidate has said anything.
    { type: "skip", needsEmpty: true, res: [/^(?:next question|(?:can we |let's |lets )?move on)$/] },
    { type: "end", res: [
      /^(?:i want to|i'd like to|i would like to|let's|lets|can we|can i) (?:end|stop|finish) (?:the|this) interview(?: here)?$/,
      /^(?:end|stop|finish) (?:the|this) interview(?: here)?$/,
    ] },
    { type: "clear", res: [
      /^(?:clear|delete|erase|scratch) (?:my|the|that) answer$/,
      /^(?:let me |can i )?start (?:over|again)$/,
    ] },
    { type: "slower", res: [/^(?:(?:can|could) you )?(?:speak|talk) (?:a bit |a little )?(?:more )?(?:slower|slowly)$/, /^slow down$/] },
    { type: "faster", res: [/^(?:(?:can|could) you )?(?:speak|talk) (?:a bit |a little )?faster$/, /^speed up$/] },
  ];

  /** A command spoken on its own, or null. */
  function detect(segment, opts) {
    const answerEmpty = !opts || opts.answerEmpty !== false;
    const c = core(segment);
    if (!c || words(c) > MAX_COMMAND_WORDS) return null;
    for (const cmd of COMMANDS) {
      if (cmd.needsEmpty && !answerEmpty) continue;
      if (cmd.res.some((re) => re.test(c))) return { type: cmd.type };
    }
    return null;
  }

  const SUBMIT = /^(?:(?:that's|that is|this is|and that's|so that's) (?:my|the) (?:final )?answer|(?:i'm|i am|and i'm) done(?: with (?:my|the|this) answer)?|(?:submit|send) (?:my |the )?answer|(?:that's|that is) (?:all|it)(?: from my side| from me)?|over to you)$/;

  /** If the answer ends with "that's my answer" etc., return the answer without it; otherwise null. */
  function stripSubmit(text) {
    const parts = String(text || "").trim().split(/\s+/).filter(Boolean);
    for (let k = Math.min(8, parts.length); k >= 1; k--) {
      if (SUBMIT.test(core(parts.slice(-k).join(" ")))) {
        return parts.slice(0, -k).join(" ").replace(/[\s,;:.-]+$/, "").replace(/\s+(?:so|and|okay|ok)$/i, "").trim();
      }
    }
    return null;
  }

  const YES = /^(?:yes|yeah|yep|yup|sure|confirm|correct|go ahead|do it|end it)(?: (?:yes|end it|please|do it|go ahead|end the interview))*$/;
  const NO = /^(?:no|nope|nah|cancel|continue|keep going|not yet|don't|do not)(?: (?:no|thanks|thank you|let's continue|lets continue|continue|keep going|not yet))*$/;
  /** true / false for a yes-no reply, null if unclear. */
  function confirm(text) {
    // Lighter cleanup than core(): "yeah" and "sure" are the answer here, not padding.
    const c = norm(text).replace(TRAIL, "").replace(/^(?:(?:okay|ok|um+|uh+|hmm+|well)\s+)+/, "").trim();
    if (YES.test(c)) return true;
    if (NO.test(c)) return false;
    return null;
  }

  const FILLERS = new Set(["so", "and", "um", "umm", "uh", "uhh", "like", "but", "because", "then", "the", "a", "an",
    "of", "to", "which", "basically", "or", "if", "with", "for", "is", "we", "i", "my", "that", "where", "when"]);
  /** Ends mid-thought ("...and so") -> wait longer before auto-sending. */
  function endsMidThought(text) {
    const n = norm(text);
    return !!n && FILLERS.has(n.split(" ").pop());
  }

  const api = { detect, stripSubmit, confirm, endsMidThought, words, norm };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.VoiceCommands = api;
})(typeof window !== "undefined" ? window : globalThis);
