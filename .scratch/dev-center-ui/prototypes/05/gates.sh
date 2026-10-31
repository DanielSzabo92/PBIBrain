#!/bin/sh
# Run the kit state gate (through gate.mjs) and the target size gate on each static page. Prototype only.
K=/C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/scripts
for f in pages/*.html; do
  P=$(cd pages && pwd -W)/$(basename "$f")
  out=$(DS_REQUIRE_BROWSER=1 node --input-type=module -e "process.argv=[process.argv[0],'$K/gate.mjs','verify_states.mjs','$P']; await import('file://$K/gate.mjs')" 2>&1)
  echo "$(basename $f): $(echo "$out" | grep -E 'OK|FAIL|SKIP|PASS' | head -3 | tr '\n' ' ')"
  echo "$out" | grep ' x ' | head -5
done
