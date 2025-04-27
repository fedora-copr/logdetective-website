// Calculating offset of a selected text within an element is a hard problem.
//
// There are many relevant inconsistencies between browsers:
// - In Firefox, `anchorNode` is the parent node, in Chrome it's the text node
//   itself.
// - In Firefox, `previousSibling` can also return the parent node. Also,
//   in Firefox it skips over text nodes and returns only element nodes.
//   In Chrome it returns both.
// - For performance reasons, browsers split long text nodes into multiple
//   smaller text nodes. In Firefox the length threshold seem to be 65536
//   characters. I didn't see it happen in Chrome yet.
// - There are probably many others.
//
// The following code is a result of a long vibe coding session with ChatGPT,
// and it is the first solution that seems to work correctly in both Firefox
// and Chrome. I could rewrite it ClojureScript to fit our codebase better,
// but I don't want to risk introducing accidental bugs.

function getAbsoluteOffsetInContainer(containerId) {
  const selection = window.getSelection();
  if (!selection.rangeCount) return 0;

  const range = selection.getRangeAt(0);
  const container = document.getElementById(containerId);
  const startNode = range.startContainer;
  const startOffset = range.startOffset;

  let offset = 0;
  let found = false;

  function traverse(node) {
    if (!node || found) return; // Extra safety: node could be null!

    if (node === startNode) {
      if (node.nodeType === Node.TEXT_NODE) {
        offset += startOffset;
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        // If selection is inside an element, we must count up to child at startOffset
        let childCount = node.childNodes.length;
        for (let i = 0; i < startOffset && i < childCount; i++) {
          offset += getTextLength(node.childNodes[i]);
        }
      }
      found = true;
      return;
    }

    if (node.nodeType === Node.TEXT_NODE) {
      offset += node.textContent.length;
    }

    for (let i = 0; i < node.childNodes.length; i++) {
      traverse(node.childNodes[i]);
      if (found) break;
    }
  }

  traverse(container);
  return offset;
}


// Helper to sum text inside an element
function getTextLength(node) {
  let length = 0;
  node.childNodes.forEach(child => {
    if (child.nodeType === Node.TEXT_NODE) {
      length += child.textContent.length;
    } else if (child.nodeType === Node.ELEMENT_NODE) {
      length += getTextLength(child);
    }
  });
  return length;
}
