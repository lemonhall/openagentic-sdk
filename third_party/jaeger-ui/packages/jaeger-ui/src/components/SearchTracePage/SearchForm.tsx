// Copyright (c) 2017 Uber Technologies, Inc.
// SPDX-License-Identifier: Apache-2.0

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { Input, Button, Popover, Select, Row, Col, Form, Switch } from 'antd';
import _get from 'lodash/get';
import logfmtParser from 'logfmt/lib/logfmt_parser';
import { stringify as logfmtStringify } from 'logfmt/lib/stringify';
import dayjs from 'dayjs';
import memoizeOne from 'memoize-one';
import queryString from 'query-string';
import { IoHelp } from 'react-icons/io5';
import { connect, ConnectedProps } from 'react-redux';
import { bindActionCreators, Dispatch } from 'redux';
import store from 'store';

import * as markers from './SearchForm.markers';
import { trackFormInput } from './SearchForm.track';
import * as jaegerApiActions from '../../actions/jaeger-api';
import { formatDate, formatTime } from '../../utils/date';
import { DEFAULT_OPERATION, DEFAULT_LIMIT, DEFAULT_LOOKBACK } from '../../constants/search-form';
import { getConfigValue } from '../../utils/config/get-config';
import SearchableSelect from '../common/SearchableSelect';
import './SearchForm.css';
import ValidatedFormField from '../../utils/ValidatedFormField';
import LoadingIndicator from '../common/LoadingIndicator';
import { useConfig } from '../../hooks/useConfig';
import { useServices, useSpanNames } from '../../hooks/useTraceDiscovery';
import { ReduxState } from '../../types';
import { SearchQuery } from '../../types/search';
import { fetchedState } from '../../constants';

const FormItem = Form.Item;
const Option = Select.Option;

const ADJUST_TIME_ENABLED_KEY = 'jaeger-ui/search-adjust-time-enabled';

interface TimeStampParams {
  startDate: string;
  startDateTime: string;
  endDate: string;
  endDateTime: string;
}

interface TimeStampResult {
  start: string;
  end: string;
}

export function getUnixTimeStampInMSFromForm({
  startDate,
  startDateTime,
  endDate,
  endDateTime,
}: TimeStampParams): TimeStampResult {
  const start = `${startDate} ${startDateTime}`;
  const end = `${endDate} ${endDateTime}`;
  return {
    start: `${dayjs(start, 'YYYY-MM-DD HH:mm').valueOf()}000`,
    end: `${dayjs(end, 'YYYY-MM-DD HH:mm').valueOf()}000`,
  };
}

export function convTagsLogfmt(tags: string | null | undefined): string | null {
  if (!tags) {
    return null;
  }
  const data = logfmtParser.parse(tags);
  Object.keys(data).forEach(key => {
    const value = data[key];
    // make sure all values are strings
    // https://github.com/jaegertracing/jaeger/issues/550#issuecomment-352850811
    if (typeof value !== 'string') {
      data[key] = String(value);
    }
  });
  return JSON.stringify(data);
}

export function lookbackToTimestamp(lookback: string, from: Date | number): number {
  const unit = lookback.substr(-1) as any; // dayjs ManipulateType
  return dayjs(from).subtract(parseInt(lookback, 10), unit).valueOf() * 1000;
}

interface ILookbackOption {
  label: string;
  value: string;
}

const LOOKBACK_LABELS: Record<string, string> = {
  '5 Minutes': '5 分钟',
  '15 Minutes': '15 分钟',
  '30 Minutes': '30 分钟',
  Hour: '1 小时',
  '2 Hours': '2 小时',
  '3 Hours': '3 小时',
  '6 Hours': '6 小时',
  '12 Hours': '12 小时',
  '24 Hours': '24 小时',
  '2 Days': '2 天',
  '3 Days': '3 天',
  '5 Days': '5 天',
  '7 Days': '7 天',
  '2 Weeks': '2 周',
  '3 Weeks': '3 周',
  '4 Weeks': '4 周',
};

function translateLookbackLabel(label: string): string {
  return LOOKBACK_LABELS[label] || label;
}

const lookbackOptions: ILookbackOption[] = [
  {
    label: '5 Minutes',
    value: '5m',
  },
  {
    label: '15 Minutes',
    value: '15m',
  },
  {
    label: '30 Minutes',
    value: '30m',
  },
  {
    label: 'Hour',
    value: '1h',
  },
  {
    label: '2 Hours',
    value: '2h',
  },
  {
    label: '3 Hours',
    value: '3h',
  },
  {
    label: '6 Hours',
    value: '6h',
  },
  {
    label: '12 Hours',
    value: '12h',
  },
  {
    label: '24 Hours',
    value: '24h',
  },
  {
    label: '2 Days',
    value: '2d',
  },
  {
    label: '3 Days',
    value: '3d',
  },
  {
    label: '5 Days',
    value: '5d',
  },
  {
    label: '7 Days',
    value: '7d',
  },
  {
    label: '2 Weeks',
    value: '2w',
  },
  {
    label: '3 Weeks',
    value: '3w',
  },
  {
    label: '4 Weeks',
    value: '4w',
  },
];

export const optionsWithinMaxLookback = memoizeOne((maxLookback: ILookbackOption) => {
  const now = new Date();
  const minTimestamp = lookbackToTimestamp(maxLookback.value, now);
  const lookbackToTimestampMap = new Map<string, number>();
  const options = lookbackOptions.filter(({ value }) => {
    const lookbackTimestamp = lookbackToTimestamp(value, now);
    lookbackToTimestampMap.set(value, lookbackTimestamp);
    return lookbackTimestamp >= minTimestamp;
  });
  const lastInRangeIndex = options.length - 1;
  const lastInRangeOption = options[lastInRangeIndex];
  if (lastInRangeOption.label !== maxLookback.label) {
    if (lookbackToTimestampMap.get(lastInRangeOption.value) !== minTimestamp) {
      options.push(maxLookback);
    } else {
      options.splice(lastInRangeIndex, 1, maxLookback);
    }
  }
  return options.map(({ label, value }) => (
    <Option key={value} value={value}>
      {`最近 ${translateLookbackLabel(label)}`}
    </Option>
  ));
});

export function traceIDsToQuery(traceIDs: string | null | undefined): string[] | null {
  if (!traceIDs) {
    return null;
  }
  return traceIDs.split(',');
}

export const placeholderDurationFields = '例如 1.2s、100ms、500us';

interface ValidationError {
  content: string;
  title: string;
}

export function validateDurationFields(value: string | null | undefined): ValidationError | undefined {
  if (!value) return undefined;
  return /\d[\d.]*( us|ms|s|m|h)$/.test(value)
    ? undefined
    : {
        content: `请输入数字并追加耗时单位，${placeholderDurationFields}`,
        title: '请输入符合要求的格式。',
      };
}

interface QueryParams {
  start?: string;
  end?: string;
}

interface FormDates {
  queryStartDate?: string;
  queryStartDateTime?: string;
  queryEndDate?: string;
  queryEndDateTime?: string;
}

export function convertQueryParamsToFormDates({ start, end }: QueryParams): FormDates {
  let queryStartDate: string | undefined;
  let queryStartDateTime: string | undefined;
  let queryEndDate: string | undefined;
  let queryEndDateTime: string | undefined;
  if (end) {
    const endUnixNs = parseInt(end, 10);
    queryEndDate = formatDate(endUnixNs);
    queryEndDateTime = formatTime(endUnixNs);
  }
  if (start) {
    const startUnixNs = parseInt(start, 10);
    queryStartDate = formatDate(startUnixNs);
    queryStartDateTime = formatTime(startUnixNs);
  }

  return {
    queryStartDate,
    queryStartDateTime,
    queryEndDate,
    queryEndDateTime,
  };
}

// Applies time adjustment to shift end time back by the specified duration
// This helps avoid incomplete traces that may still be receiving spans
export function applyAdjustTime(endTimestamp: number, adjustTime: string | null | undefined): number {
  if (!adjustTime) {
    return endTimestamp;
  }
  const adjustedEnd = lookbackToTimestamp(adjustTime, endTimestamp / 1000);
  return adjustedEnd;
}

interface ISearchFormFields {
  resultsLimit: string;
  service: string;
  startDate: string;
  startDateTime: string;
  endDate: string;
  endDateTime: string;
  operation: string;
  tags?: string;
  minDuration?: string;
  maxDuration?: string;
  lookback: string;
}

type SearchTracesFunction = typeof jaegerApiActions.searchTraces;

export function submitForm(
  fields: ISearchFormFields,
  searchTraces: SearchTracesFunction,
  adjustTime: string | null | undefined,
  adjustTimeEnabled: boolean
): void {
  const {
    resultsLimit,
    service,
    startDate,
    startDateTime,
    endDate,
    endDateTime,
    operation,
    tags,
    minDuration,
    maxDuration,
    lookback,
  } = fields;
  // Note: traceID is ignored when the form is submitted
  store.set('lastSearch', { service, operation });

  let start: string | number;
  let end: number;
  if (lookback !== 'custom') {
    const now = new Date();
    start = String(lookbackToTimestamp(lookback, now));
    end = now.valueOf() * 1000;
  } else {
    const times = getUnixTimeStampInMSFromForm({
      startDate,
      startDateTime,
      endDate,
      endDateTime,
    });
    start = times.start;
    end = parseInt(times.end, 10);
  }

  // Apply time adjustment to exclude very recent traces that may be incomplete
  if (adjustTimeEnabled) {
    end = applyAdjustTime(end, adjustTime);
  }

  trackFormInput(resultsLimit, operation, tags || '', minDuration, maxDuration, lookback, service);

  searchTraces({
    service,
    operation: operation !== DEFAULT_OPERATION ? operation : undefined,
    limit: resultsLimit,
    lookback,
    start: String(start),
    end: String(end),
    tags: convTagsLogfmt(tags) || undefined,
    minDuration: minDuration || null,
    maxDuration: maxDuration || null,
  } as SearchQuery);
}

interface ISearchFormImplProps {
  invalid?: boolean;
  submitting?: boolean;
  searchMaxLookback?: ILookbackOption;
  searchAdjustEndTime?: string;
  initialValues?: Partial<ISearchFormFields> & { traceIDs?: string | null };
  searchTraces: SearchTracesFunction;
  submitFormHandler: (
    fields: ISearchFormFields,
    adjustEndTime: string | null | undefined,
    adjustTimeEnabled: boolean
  ) => void;
}

export const SearchFormImpl: React.FC<ISearchFormImplProps> = ({
  invalid = false,
  submitting = false,
  searchMaxLookback,
  searchAdjustEndTime,
  initialValues,
  submitFormHandler,
}) => {
  const { useOpenTelemetryTerms: useOtelTerms } = useConfig();
  const [formData, setFormData] = useState<Partial<ISearchFormFields>>(() => ({
    service: initialValues?.service,
    operation: initialValues?.operation,
    tags: initialValues?.tags,
    lookback: initialValues?.lookback,
    startDate: initialValues?.startDate,
    startDateTime: initialValues?.startDateTime,
    endDate: initialValues?.endDate,
    endDateTime: initialValues?.endDateTime,
    minDuration: initialValues?.minDuration,
    maxDuration: initialValues?.maxDuration,
    resultsLimit: initialValues?.resultsLimit,
  }));

  // Fetch services using React Query
  const { data: services = [], isLoading: isLoadingServices, error: servicesError } = useServices();

  // Fetch span names for the currently selected service
  const currentService = formData.service;
  const {
    data: spanNamesData,
    isLoading: isLoadingSpanNames,
    error: spanNamesError,
  } = useSpanNames(currentService && currentService !== '-' ? currentService : null);

  // Extract unique operation names from span data
  // API returns { name, spanKind }[] where the same name can appear with different spanKinds
  // We deduplicate to show only unique names in the operations dropdown
  const spanNames = useMemo(
    () => Array.from(new Set((spanNamesData || []).map(op => op.name))).sort(),
    [spanNamesData]
  );

  const [adjustTimeEnabled, setAdjustTimeEnabled] = useState<boolean>(() => {
    const storedAdjustTimeEnabled = store.get(ADJUST_TIME_ENABLED_KEY);
    return storedAdjustTimeEnabled !== undefined ? storedAdjustTimeEnabled : Boolean(searchAdjustEndTime);
  });

  const handleChange = useCallback((fieldData: Partial<ISearchFormFields>) => {
    setFormData(prev => {
      const nextFormData = { ...prev, ...fieldData };
      if (fieldData.service) {
        nextFormData.operation = DEFAULT_OPERATION;
      }
      return nextFormData;
    });
  }, []);

  const handleAdjustTimeToggle = useCallback((checked: boolean) => {
    setAdjustTimeEnabled(checked);
    store.set(ADJUST_TIME_ENABLED_KEY, checked);
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      submitFormHandler(formData as ISearchFormFields, searchAdjustEndTime, adjustTimeEnabled);
    },
    [formData, searchAdjustEndTime, adjustTimeEnabled, submitFormHandler]
  );

  const { service: selectedService, lookback: selectedLookback } = formData;
  const noSelectedService = selectedService === '-' || !selectedService;
  const tz = selectedLookback === 'custom' ? new Date().toTimeString().replace(/^.*?GMT/, 'UTC') : null;
  const invalidDuration =
    validateDurationFields(formData.minDuration) || validateDurationFields(formData.maxDuration);

  if (isLoadingServices && services.length === 0 && !servicesError) {
    return <LoadingIndicator />;
  }

  return (
    <Form layout="vertical" onSubmitCapture={handleSubmit}>
      <FormItem
        label={
          <span>
            服务 <span className="SearchForm--labelCount">({services.length})</span>
          </span>
        }
        validateStatus={servicesError ? 'error' : undefined}
        help={servicesError ? `加载服务失败：${(servicesError as Error).message}` : undefined}
      >
        <SearchableSelect
          data-testid="service"
          value={formData.service}
          placeholder="选择服务"
          disabled={submitting}
          loading={isLoadingServices}
          onChange={(value: string) => handleChange({ service: value })}
        >
          {services.map(serviceName => (
            <Option key={serviceName} value={serviceName}>
              {serviceName}
            </Option>
          ))}
        </SearchableSelect>
      </FormItem>
      <FormItem
        label={
          <span>
            {useOtelTerms ? 'Span 名称' : '操作'}{' '}
            <span className="SearchForm--labelCount">({spanNames.length})</span>
          </span>
        }
        validateStatus={spanNamesError ? 'error' : undefined}
        help={spanNamesError ? `加载操作列表失败：${(spanNamesError as Error).message}` : undefined}
      >
        <SearchableSelect
          data-testid="operation"
          value={formData.operation}
          disabled={submitting || noSelectedService}
          loading={isLoadingSpanNames}
          placeholder={useOtelTerms ? '选择 Span 名称' : '选择操作'}
          onChange={(value: string) => handleChange({ operation: value })}
        >
          {['all'].concat(spanNames).map(op => (
            <Option key={op} value={op}>
              {op === 'all' ? '全部' : op}
            </Option>
          ))}
        </SearchableSelect>
      </FormItem>

      <FormItem
        label={
          <div>
            {useOtelTerms ? '属性' : '标签'}{' '}
            <Popover
              placement="topLeft"
              trigger="click"
              title={
                <h3 key="title" className="SearchForm--tagsHintTitle">
                  值需要使用{' '}
                  <a href="https://brandur.org/logfmt" rel="noopener noreferrer" target="_blank">
                    logfmt
                  </a>{' '}
                  格式。
                </h3>
              }
              content={
                <div>
                  <ul key="info" className="SearchForm--tagsHintInfo">
                    <li>使用空格表示 AND 组合条件。</li>
                    <li>
                      含空格或等号 `=` 的值需要放在引号里。
                    </li>
                    <li>
                      Elasticsearch/OpenSearch 存储支持正则查询，因此{' '}
                      <a
                        href="https://lucene.apache.org/core/9_0_0/core/org/apache/lucene/util/automaton/RegExp.html"
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        保留字符
                      </a>{' '}
                      在精确匹配时需要转义。
                    </li>
                  </ul>
                  <p>示例：</p>
                  <ul className="SearchForm--tagsHintInfo">
                    <li>
                      <code className="SearchForm--tagsHintEg">error=true</code>
                    </li>
                    <li>
                      <code className="SearchForm--tagsHintEg">
                        db.statement=&quot;select * from User&quot;
                      </code>
                    </li>
                    <li>
                      <code className="SearchForm--tagsHintEg">
                        http.url=&quot;http://0.0.0.0:8081/customer\\?customer=123&quot;
                      </code>
                      <div>
                        注意：使用 Elasticsearch/OpenSearch 时，{' '}
                        <a
                          href="https://lucene.apache.org/core/9_0_0/core/org/apache/lucene/util/automaton/RegExp.html"
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          正则保留
                        </a>{' '}
                        字符 <code className="SearchForm--tagsHintEg">&quot;?&quot;</code> 必须使用{' '}
                        <code className="SearchForm--tagsHintEg">&quot;\\&quot;</code> 转义。
                      </div>
                    </li>
                  </ul>
                </div>
              }
            >
              <IoHelp className="SearchForm--hintTrigger" />
            </Popover>
          </div>
        }
      >
        <Input
          name="tags"
          value={formData.tags}
          disabled={submitting}
          placeholder="http.status_code=200 error=true"
          onChange={e => handleChange({ tags: e.target.value })}
          allowClear
        />
      </FormItem>

      <div className="SearchForm--lookbackRow">
        <span className="SearchForm--lookbackLabel">回看范围</span>
        {searchAdjustEndTime && (
          <div className="SearchForm--adjustTime">
            <span className="SearchForm--adjustTimeLabel">向前调整 -{searchAdjustEndTime}</span>
            <Switch
              size="small"
              checked={adjustTimeEnabled}
              onChange={handleAdjustTimeToggle}
              disabled={submitting}
            />
            <Popover
              placement="topLeft"
              trigger="click"
              content={
                <div className="SearchForm--lookbackHint">
                  启用后，搜索结束时间会向前回退 {searchAdjustEndTime}，以排除仍在持续接收 span 的最新
                  Trace。
                </div>
              }
            >
              <IoHelp className="SearchForm--hintTrigger" />
            </Popover>
          </div>
        )}
      </div>
      <FormItem>
        <SearchableSelect
          data-testid="lookback"
          value={formData.lookback}
          disabled={submitting}
          defaultValue={DEFAULT_LOOKBACK}
          onChange={(value: string) => handleChange({ lookback: value })}
        >
          {searchMaxLookback && optionsWithinMaxLookback(searchMaxLookback)}
          <Option value="custom">自定义时间范围</Option>
        </SearchableSelect>
      </FormItem>

      {selectedLookback === 'custom' && [
        <FormItem
          key="start"
          label={
            <div>
              开始时间{' '}
              <Popover
                placement="topLeft"
                trigger="click"
                content={
                  <h3 key="title" className="SearchForm--tagsHintTitle">
                    当前时间使用 {tz}
                  </h3>
                }
              >
                <IoHelp className="SearchForm--hintTrigger" />
              </Popover>
            </div>
          }
        >
          <Row gutter={16}>
            <Col className="gutter-row" span={14}>
              <Input
                name="startDate"
                value={formData.startDate}
                disabled={submitting}
                type="date"
                placeholder="开始日期"
                onChange={e => handleChange({ startDate: e.target.value })}
              />
            </Col>

            <Col className="gutter-row" span={10}>
              <Input
                name="startDateTime"
                value={formData.startDateTime}
                disabled={submitting}
                type="time"
                onChange={e => handleChange({ startDateTime: e.target.value })}
              />
            </Col>
          </Row>
        </FormItem>,

        <FormItem
          key="end"
          label={
            <div>
              结束时间{' '}
              <Popover
                placement="topLeft"
                trigger="click"
                content={
                  <h3 key="title" className="SearchForm--tagsHintTitle">
                    当前时间使用 {tz}
                  </h3>
                }
              >
                <IoHelp className="SearchForm--hintTrigger" />
              </Popover>
            </div>
          }
        >
          <Row gutter={16}>
            <Col className="gutter-row" span={14}>
              <Input
                name="endDate"
                value={formData.endDate}
                disabled={submitting}
                type="date"
                placeholder="结束日期"
                onChange={e => handleChange({ endDate: e.target.value })}
              />
            </Col>

            <Col className="gutter-row" span={10}>
              <Input
                name="endDateTime"
                value={formData.endDateTime}
                disabled={submitting}
                type="time"
                onChange={e => handleChange({ endDateTime: e.target.value })}
              />
            </Col>
          </Row>
        </FormItem>,
      ]}

      <Row gutter={16}>
        <Col className="gutter-row" span={12}>
          <FormItem label="最大耗时">
            <ValidatedFormField
              name="maxDuration"
              value={formData.maxDuration}
              disabled={submitting}
              validate={validateDurationFields}
              placeholder={placeholderDurationFields}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                handleChange({ maxDuration: e.target.value })
              }
            />
          </FormItem>
        </Col>

        <Col className="gutter-row" span={12}>
          <FormItem label="最小耗时">
            <ValidatedFormField
              name="minDuration"
              value={formData.minDuration}
              disabled={submitting}
              validate={validateDurationFields}
              placeholder={placeholderDurationFields}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                handleChange({ minDuration: e.target.value })
              }
            />
          </FormItem>
        </Col>
      </Row>

      <FormItem label="结果上限">
        <Input
          name="resultsLimit"
          value={formData.resultsLimit}
          disabled={submitting}
          placeholder="结果上限"
          type="number"
          min={1}
          max={getConfigValue('search.maxLimit')}
          onChange={e => handleChange({ resultsLimit: e.target.value })}
        />
      </FormItem>

      <Button
        htmlType="submit"
        className="SearchForm--submit"
        disabled={submitting || noSelectedService || invalid || invalidDuration !== undefined}
        data-test={markers.SUBMIT_BTN}
      >
        搜索 Trace
      </Button>
    </Form>
  );
};

export function mapStateToProps(state: ReduxState) {
  const {
    service,
    limit,
    start,
    end,
    operation,
    tag: tagParams,
    tags: logfmtTags,
    maxDuration,
    minDuration,
    lookback,
    traceID: traceIDParams,
  } = queryString.parse(state.router.location.search);

  const nowInMicroseconds = dayjs().valueOf() * 1000;
  const today = formatDate(nowInMicroseconds);
  const currentTime = formatTime(nowInMicroseconds);
  const lastSearch = store.get('lastSearch') as { service?: string; operation?: string } | undefined;
  let lastSearchService: string | undefined;
  let lastSearchOperation: string | undefined;

  if (lastSearch) {
    const { operation: lastOp, service: lastSvc } = lastSearch;
    if (lastSvc && lastSvc !== '-') {
      lastSearchService = lastSvc;
      if (lastOp && lastOp !== '-') {
        lastSearchOperation = lastOp;
      }
    }
  }

  const { queryStartDate, queryStartDateTime, queryEndDate, queryEndDateTime } =
    convertQueryParamsToFormDates({
      start: start as string | undefined,
      end: end as string | undefined,
    });

  let tags: string | undefined;
  // continue to parse tagParams to remain backward compatible with older URLs
  // but, parse to logfmt format instead of the former "key:value|k2:v2"
  if (tagParams) {
    function convFormerTag(accum: Record<string, string>, value: string): boolean {
      const parts = value.split(':', 2);
      const key = parts[0];
      if (key) {
        accum[key] = parts[1] == null ? '' : parts[1];
        return true;
      }
      return false;
    }

    let data: Record<string, string> | null = null;
    if (Array.isArray(tagParams)) {
      data = tagParams
        .filter((str): str is string => !!str) // skip null, undefined, empty strings
        .reduce(
          (accum, str) => {
            convFormerTag(accum, str);
            return accum;
          },
          {} as Record<string, string>
        );
    } else if (typeof tagParams === 'string') {
      const target: Record<string, string> = {};
      data = convFormerTag(target, tagParams) ? target : null;
    }
    if (data) {
      try {
        tags = logfmtStringify(data);
      } catch (_) {
        tags = '解析失败';
      }
    } else {
      tags = '解析失败';
    }
  }
  if (logfmtTags) {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(logfmtTags as string);
      tags = logfmtStringify(data);
    } catch (_) {
      tags = '解析失败';
    }
  }
  let traceIDs: string | undefined;
  if (traceIDParams) {
    traceIDs = traceIDParams instanceof Array ? traceIDParams.join(',') : (traceIDParams as string);
  }

  return {
    destroyOnUnmount: false,
    initialValues: {
      service: (service as string | undefined) || lastSearchService || '-',
      resultsLimit: (limit as string | undefined) || String(DEFAULT_LIMIT),
      lookback: (lookback as string | undefined) || DEFAULT_LOOKBACK,
      startDate: queryStartDate || today,
      startDateTime: queryStartDateTime || '00:00',
      endDate: queryEndDate || today,
      endDateTime: queryEndDateTime || currentTime,
      operation: (operation as string | undefined) || lastSearchOperation || DEFAULT_OPERATION,
      tags,
      minDuration: (minDuration as string | undefined) || undefined,
      maxDuration: (maxDuration as string | undefined) || undefined,
      traceIDs: traceIDs || null,
    },
    searchMaxLookback: _get(state, 'config.search.maxLookback'),
    searchAdjustEndTime: _get(state, 'config.search.adjustEndTime'),
    submitting: state.trace?.search?.state === fetchedState.LOADING,
  };
}

export function mapDispatchToProps(dispatch: Dispatch) {
  const { searchTraces } = bindActionCreators(jaegerApiActions, dispatch);
  return {
    searchTraces,
    submitFormHandler: (
      fields: ISearchFormFields,
      adjustEndTime: string | null | undefined,
      adjustTimeEnabled: boolean
    ) => submitForm(fields, searchTraces, adjustEndTime || null, adjustTimeEnabled),
  };
}

const connector = connect(mapStateToProps, mapDispatchToProps);
type PropsFromRedux = ConnectedProps<typeof connector>;

export default connector(SearchFormImpl);
