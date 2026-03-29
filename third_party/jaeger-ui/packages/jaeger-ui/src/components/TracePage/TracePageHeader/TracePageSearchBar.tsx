// Copyright (c) 2018 Uber Technologies, Inc.
// SPDX-License-Identifier: Apache-2.0

import * as React from 'react';
import { Button, Input, InputRef, Tooltip } from 'antd';
import cx from 'classnames';
import { IoLocate, IoHelp, IoClose, IoChevronDown, IoChevronUp } from 'react-icons/io5';

import * as markers from './TracePageSearchBar.markers';
import { trackFilter } from '../index.track';
import UiFindInput from '../../common/UiFindInput';
import { TNil } from '../../../types';
import './TracePageSearchBar.css';

type TracePageSearchBarProps = {
  textFilter: string | TNil;
  prevResult: () => void;
  nextResult: () => void;
  clearSearch: () => void;
  focusUiFindMatches: () => void;
  resultCount: number;
  navigable: boolean;
  useOtelTerms: boolean;
};

export function TracePageSearchBarFn(props: TracePageSearchBarProps & { forwardedRef: React.Ref<InputRef> }) {
  const {
    focusUiFindMatches,
    forwardedRef,
    navigable,
    nextResult,
    prevResult,
    resultCount,
    textFilter,
    useOtelTerms,
  } = props;

  const count = textFilter ? <span className="TracePageSearchBar--count">{resultCount}</span> : null;

  const btnClass = cx('TracePageSearchBar--btn', { 'is-disabled': !textFilter });
  const uiFindInputInputProps = {
    'data-test': markers.IN_TRACE_SEARCH,
    className: 'TracePageSearchBar--bar ub-flex-auto',
    name: 'search',
    placeholder: useOtelTerms ? '搜索 Span、属性、事件...' : '搜索操作、标签、日志...',
    suffix: count,
  };

  const renderTooltip = () => {
    return (
      <div style={{ wordBreak: 'normal' }}>
        <p>
          这是页内搜索。请输入由空格分隔的一组关键词。每个关键词都会对以下内容做子串匹配：服务名、
          {useOtelTerms ? 'Span 名称' : '操作名'}、Span ID，以及
          {useOtelTerms ? '属性与事件' : '标签与日志'}中的键值对。命中的 Span 会被高亮显示。
        </p>
        <p>
          如果要做精确短语搜索，请把查询内容放进双引号里，例如 <code>&quot;The quick brown fox&quot;</code>
        </p>
        <p>
          匹配键值对时，会分别对 key、value，以及拼接后的 <code>&quot;key=value&quot;</code>{' '}
          字符串做子串匹配。因此你可以直接搜索 <code>http.status_code=200</code> 这类精确键值。
        </p>
        <p>
          如果想排除某些键值对参与匹配，可以在 key 前加减号 <code>&apos;-&apos;</code>，例如{' '}
          <code>-http.status_code</code>。
        </p>
      </div>
    );
  };

  return (
    <div className="TracePageSearchBar">
      {/* style inline because compact overwrites the display */}
      <Input.Group className="ub-justify-end" compact style={{ display: 'flex' }}>
        <UiFindInput
          inputProps={uiFindInputInputProps}
          forwardedRef={forwardedRef}
          trackFindFunction={trackFilter}
        />
        <Tooltip
          arrow={{ pointAtCenter: true }}
          placement="bottomLeft"
          trigger="hover"
          overlayStyle={{ maxWidth: '600px' }} // This is a large tooltip and the default is too narrow.
          title={renderTooltip()}
        >
          <div className="help-btn-container">
            <IoHelp className="help-button" />
          </div>
        </Tooltip>
        {navigable && (
          <>
            <Button
              className={cx(btnClass, 'TracePageSearchBar--locateBtn')}
              disabled={!textFilter}
              htmlType="button"
              onClick={focusUiFindMatches}
            >
              <IoLocate />
            </Button>
            <Button
              className={cx(btnClass, 'TracePageSearchBar--ButtonUp')}
              disabled={!textFilter}
              htmlType="button"
              data-testid="UpOutlined"
              onClick={prevResult}
            >
              <IoChevronUp />
            </Button>
            <Button
              className={cx(btnClass, 'TracePageSearchBar--ButtonDown')}
              disabled={!textFilter}
              htmlType="button"
              data-testid="DownOutlined"
              onClick={nextResult}
            >
              <IoChevronDown />
            </Button>
          </>
        )}
      </Input.Group>
    </div>
  );
}

export default React.forwardRef((props: TracePageSearchBarProps, ref: React.Ref<InputRef>) => (
  <TracePageSearchBarFn {...props} forwardedRef={ref} />
));
