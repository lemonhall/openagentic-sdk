// Copyright (c) 2017 Uber Technologies, Inc.
// SPDX-License-Identifier: Apache-2.0

const keyboardMappings: Record<string, { binding: string | string[]; label: string }> = {
  scrollPageDown: { binding: 's', label: '向下滚动' },
  scrollPageUp: { binding: 'w', label: '向上滚动' },
  scrollToNextVisibleSpan: { binding: 'f', label: '跳到下一个可见 Span' },
  scrollToPrevVisibleSpan: { binding: 'b', label: '跳到上一个可见 Span' },
  panLeft: { binding: ['a', 'left'], label: '向左平移' },
  panLeftFast: { binding: ['shift+a', 'shift+left'], label: '向左平移，大步' },
  panRight: { binding: ['d', 'right'], label: '向右平移' },
  panRightFast: { binding: ['shift+d', 'shift+right'], label: '向右平移，大步' },
  zoomIn: { binding: 'up', label: '放大' },
  zoomInFast: { binding: 'shift+up', label: '放大，大步' },
  zoomOut: { binding: 'down', label: '缩小' },
  zoomOutFast: { binding: 'shift+down', label: '缩小，大步' },
  collapseAll: { binding: ']', label: '全部折叠' },
  expandAll: { binding: '[', label: '全部展开' },
  collapseOne: { binding: 'p', label: '折叠一层' },
  expandOne: { binding: 'o', label: '展开一层' },
  searchSpans: { binding: 'ctrl+b', label: '搜索 Span' },
  clearSearch: { binding: 'escape', label: '清空搜索' },
};

export default keyboardMappings;
