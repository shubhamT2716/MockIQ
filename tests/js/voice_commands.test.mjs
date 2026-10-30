import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const VC = require("../../app/static/voice-commands.js");

const expectCmd = (phrases, type, opts) => {
  for (const p of phrases) assert.deepEqual(VC.detect(p, opts), { type }, `"${p}" should be ${type}`);
};

test("recognises commands said on their own, with natural padding", () => {
  expectCmd(["Can you repeat the question?", "Sorry, could you say that again please", "Pardon?", "repeat",
    "I didn't catch that", "What was the question again?"], "repeat");
  expectCmd(["Give me a minute.", "Okay, let me think", "Can I take a moment to think?", "Hold on", "just a second"], "think");
  expectCmd(["Can I skip this one?", "I'd like to skip this question", "skip this", "Let's skip it please"], "skip");
  expectCmd(["I want to end the interview", "End the interview now", "can we stop this interview here"], "end");
  expectCmd(["clear my answer", "Let me start over"], "clear");
  expectCmd(["Can you speak slower?", "slow down please"], "slower");
  expectCmd(["speak a bit faster", "speed up"], "faster");
});

test("ignores the same words inside a real answer", () => {
  for (const p of [
    "I would skip this question of locking and use optimistic concurrency instead",
    "the client can repeat the question to the server if the request times out",
    "we end the interview loop when the queue is empty",
    "give me a minute to explain how the cache invalidation works with write through",
    "first I hash the key then I move on to the next bucket",
  ]) assert.equal(VC.detect(p), null, p);
});

test("ambiguous skip phrases only work before answering", () => {
  assert.deepEqual(VC.detect("next question", { answerEmpty: true }), { type: "skip" });
  assert.equal(VC.detect("next question", { answerEmpty: false }), null);
  assert.equal(VC.detect("let's move on", { answerEmpty: false }), null);
});

test("strips a spoken submit phrase from the end of an answer", () => {
  assert.equal(VC.stripSubmit("I'd use BFS from every land cell. That's my answer."), "I'd use BFS from every land cell");
  assert.equal(VC.stripSubmit("Use a min heap of size k, and I'm done"), "Use a min heap of size k");
  assert.equal(VC.stripSubmit("so that is my final answer"), "");
  assert.equal(VC.stripSubmit("Sharding by user id. Over to you"), "Sharding by user id");
  assert.equal(VC.stripSubmit("I'm done with the first part, now the second part is caching"), null);
  assert.equal(VC.stripSubmit("We use Redis"), null);
});

test("yes / no confirmation", () => {
  for (const y of ["Yes", "yeah please", "Yes, end it", "sure"]) assert.equal(VC.confirm(y), true, y);
  for (const n of ["No", "no, let's continue", "keep going", "not yet"]) assert.equal(VC.confirm(n), false, n);
  assert.equal(VC.confirm("maybe later we can talk about it"), null);
});

test("mid-thought endings get more time", () => {
  assert.equal(VC.endsMidThought("I would first check the cache and"), true);
  assert.equal(VC.endsMidThought("so the complexity is O(n) umm"), true);
  assert.equal(VC.endsMidThought("the complexity is O of n"), false);
  assert.equal(VC.endsMidThought(""), false);
});
