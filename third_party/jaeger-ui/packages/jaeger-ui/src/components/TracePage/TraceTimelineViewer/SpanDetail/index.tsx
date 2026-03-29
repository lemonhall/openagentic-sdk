// Copyright (c) 2017 Uber Technologies, Inc.
// SPDX-License-Identifier: Apache-2.0

import React, { useEffect, useRef } from 'react';
import { Divider } from 'antd';

import { IoLinkOutline } from 'react-icons/io5';
import AccordionAttributes from './AccordionAttributes';
import AccordionEvents from './AccordionEvents';
import AccordionLinks from './AccordionLinks';
import OaTranscriptPanel from './OaTranscriptPanel';
import AccordionText from './AccordionText';
import DetailState from './DetailState';
import { formatDuration } from '../utils';
import CopyIcon from '../../../common/CopyIcon';
import LabeledList from '../../../common/LabeledList';

import { TNil } from '../../../../types';
import { Hyperlink } from '../../../../types/hyperlink';
import { IOtelSpan, IAttribute, IEvent } from '../../../../types/otel';

import './index.css';

type SpanDetailProps = {
  detailState: DetailState;
  linksGetter: ((links: ReadonlyArray<IAttribute>, index: number) => Hyperlink[]) | TNil;
  eventItemToggle: (spanID: string, event: IEvent) => void;
  eventsToggle: (spanID: string) => void;
  resourceToggle: (spanID: string) => void;
  span: IOtelSpan;
  attributesToggle: (spanID: string) => void;
  traceStartTime: number;
  warningsToggle: (spanID: string) => void;
  linksToggle: (spanID: string) => void;
  focusSpan: (uiFind: string) => void;
  currentViewRangeTime: [number, number];
  traceDuration: number;
  useOtelTerms: boolean;
};

export default function SpanDetail(props: SpanDetailProps) {
  const {
    detailState,
    linksGetter,
    eventItemToggle,
    eventsToggle,
    resourceToggle,
    span,
    attributesToggle,
    traceStartTime,
    warningsToggle,
    linksToggle,
    focusSpan,
    currentViewRangeTime,
    traceDuration,
    useOtelTerms,
  } = props;

  const { isAttributesOpen, isResourceOpen, events: eventsState, isWarningsOpen, isLinksOpen } = detailState;
  const warnings = span.warnings;
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Get links for display in AccordionLinks
  const links = span.links || [];

  // Display labels based on terminology flag
  const attributesLabel = useOtelTerms ? 'Attributes' : 'Tags';
  const resourceLabel = useOtelTerms ? 'Resource' : 'Process';
  const eventsLabel = useOtelTerms ? 'Events' : 'Logs';

  const overviewItems = [
    {
      key: 'svc',
      label: '服务：',
      value: span.resource.serviceName,
    },
    {
      key: 'duration',
      label: '耗时：',
      value: formatDuration(span.duration),
    },
    {
      key: 'start',
      label: '起始时间：',
      value: formatDuration(span.relativeStartTime),
    },
  ];
  const deepLinkCopyText = `${window.location.origin}${window.location.pathname}?uiFind=${span.spanID}`;

  useEffect(() => {
    const element = rootRef.current;
    if (!element) {
      return undefined;
    }

    const emitDetailMeasure = () => {
      const height = Math.ceil(element.getBoundingClientRect().height);
      window.dispatchEvent(
        new CustomEvent('jaeger:detail-measure', {
          detail: {
            spanID: span.spanID,
            height,
          },
        })
      );
    };

    emitDetailMeasure();
    if (typeof ResizeObserver === 'undefined') {
      return undefined;
    }

    const observer = new ResizeObserver(() => emitDetailMeasure());
    observer.observe(element);
    return () => observer.disconnect();
  }, [detailState, span.spanID]);

  return (
    <div className="SpanDetail" ref={rootRef}>
      <div className="ub-flex ub-items-center">
        <h2 className="ub-flex-auto ub-m0">{span.name}</h2>
        <LabeledList
          className="ub-tx-right-align"
          dividerClassName="SpanDetail--divider"
          items={overviewItems}
        />
      </div>
      <Divider className="SpanDetail--divider ub-my1" />
      <div>
        <div>
          <AccordionAttributes
            data={span.attributes}
            label={attributesLabel}
            linksGetter={linksGetter}
            isOpen={isAttributesOpen}
            onToggle={() => attributesToggle(span.spanID)}
          />
          {span.resource.attributes && span.resource.attributes.length > 0 && (
            <AccordionAttributes
              className="ub-mb1"
              data={span.resource.attributes}
              label={resourceLabel}
              linksGetter={linksGetter}
              isOpen={isResourceOpen}
              onToggle={() => resourceToggle(span.spanID)}
            />
          )}
        </div>
        {span.events && span.events.length > 0 && (
          <AccordionEvents
            linksGetter={linksGetter}
            events={span.events}
            isOpen={eventsState.isOpen}
            openedItems={eventsState.openedItems}
            onToggle={() => eventsToggle(span.spanID)}
            onItemToggle={eventItem => eventItemToggle(span.spanID, eventItem)}
            timestamp={traceStartTime}
            currentViewRangeTime={currentViewRangeTime}
            traceDuration={traceDuration}
            spanID={span.spanID}
            useOtelTerms={useOtelTerms}
          />
        )}
        {warnings && warnings.length > 0 && (
          <AccordionText
            className="AccordianWarnings"
            headerClassName="AccordianWarnings--header"
            label={<span className="AccordianWarnings--label">告警</span>}
            data={warnings}
            isOpen={isWarningsOpen}
            onToggle={() => warningsToggle(span.spanID)}
          />
        )}
        {links && links.length > 0 && (
          <AccordionLinks
            data={links}
            isOpen={isLinksOpen}
            onToggle={() => linksToggle(span.spanID)}
            focusSpan={focusSpan}
            useOtelTerms={useOtelTerms}
          />
        )}
        <OaTranscriptPanel span={span} />
        <small className="SpanDetail--debugInfo">
          <span className="SpanDetail--debugLabel" data-label="SpanID：" /> {span.spanID}
          <CopyIcon
            copyText={deepLinkCopyText}
            icon={<IoLinkOutline />}
            placement="topRight"
            tooltipTitle="复制该 Span 的深链"
            buttonText="复制"
          />
        </small>
      </div>
    </div>
  );
}
