"use strict";

const { verifyMessage, getAddress } = require("ethers");
const readline = require("node:readline");

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity
});

rl.once("line", line => {
  try {
    const request = JSON.parse(line);

    if (
      typeof request.message !== "string" ||
      typeof request.signature !== "string" ||
      typeof request.address !== "string"
    ) {
      throw new Error("INVALID_INPUT");
    }

    if (
      request.message.length > 4096 ||
      request.signature.length > 1024 ||
      request.address.length > 100
    ) {
      throw new Error("INPUT_TOO_LARGE");
    }

    const expected = getAddress(request.address);
    const recovered = verifyMessage(
      request.message,
      request.signature
    );

    process.stdout.write(JSON.stringify({
      valid: recovered === expected,
      recovered
    }) + "\n");

  } catch {
    process.stdout.write(JSON.stringify({
      valid: false,
      error: "SIGNATURE_VERIFICATION_FAILED"
    }) + "\n");
  } finally {
    rl.close();
  }
});
