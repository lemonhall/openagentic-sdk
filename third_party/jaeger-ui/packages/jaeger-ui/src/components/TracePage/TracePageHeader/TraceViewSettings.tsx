// Copyright (c) 2026 The Jaeger Authors.
// SPDX-License-Identifier: Apache-2.0

import * as React from 'react';
import { Button, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { IoSettingsOutline, IoCheckmark } from 'react-icons/io5';

import KeyboardShortcutsHelp from './KeyboardShortcutsHelp';

import './TraceViewSettings.css';

type Props = {
  className?: string;
  detailPanelMode: 'inline' | 'sidepanel';
  enableSidePanel: boolean;
  onDetailPanelModeToggle: () => void;
  onTimelineToggle: () => void;
  timelineVisible: boolean;
};

const CHECK_STYLE = { marginRight: 8, fontSize: 14 };
const CHECK_PLACEHOLDER = <span style={{ display: 'inline-block', width: 22 }} />;

export default function TraceViewSettings(props: Props) {
  const {
    className,
    detailPanelMode,
    enableSidePanel,
    onDetailPanelModeToggle,
    onTimelineToggle,
    timelineVisible,
  } = props;

  const [kbdModalVisible, setKbdModalVisible] = React.useState(false);

  const items: MenuProps['items'] = [
    {
      key: 'timeline',
      icon: timelineVisible ? <IoCheckmark style={CHECK_STYLE} /> : CHECK_PLACEHOLDER,
      label: '显示时间线',
      onClick: onTimelineToggle,
    },
  ];

  if (enableSidePanel) {
    const isSidePanel = detailPanelMode === 'sidepanel';
    items.push({
      key: 'detail-panel-mode',
      icon: isSidePanel ? <IoCheckmark style={CHECK_STYLE} /> : CHECK_PLACEHOLDER,
      label: '在侧边栏显示 Span',
      onClick: onDetailPanelModeToggle,
    });
  }

  items.push(
    { type: 'divider' },
    {
      key: 'keyboard-shortcuts',
      icon: CHECK_PLACEHOLDER,
      label: '快捷键',
      onClick: () => setKbdModalVisible(true),
    }
  );

  return (
    <>
      <Dropdown menu={{ items }} trigger={['click']}>
        <Button
          className={`TraceViewSettings ${className || ''}`}
          htmlType="button"
          aria-label="Trace 视图设置"
          title="Trace 视图设置"
        >
          <IoSettingsOutline className="TraceViewSettings--icon" />
        </Button>
      </Dropdown>
      <KeyboardShortcutsHelp open={kbdModalVisible} onClose={() => setKbdModalVisible(false)} />
    </>
  );
}
