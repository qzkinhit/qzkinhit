#!/usr/bin/env python3
"""教学合成数据上的 VioExplain 原函数执行轨迹，可离线复算。

运行 python3 learning_visualizations/evidence/trace_vioexplain.py。
只在 evidence 目录写入 JSON，不修改 code_v3，也不读取/下载正式实验数据。
使用真实 DetectBackend、twin bank、ridge、120 棵树的 JointRFScorer、conformal、
AECX、LLR 指派与 Update。包装器只记录原函数输入输出，不预设评分或模型结论。
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
import math
import platform
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code_v3"))

import numpy as np
import scipy
import sklearn

import vioexplain.api.vioexplain as api
import vioexplain.core.calibrate.conformal as calibration
import vioexplain.core.detect.constraints as constraints
import vioexplain.core.detect.descriptors as descriptors
import vioexplain.core.detect.violations as violations
import vioexplain.core.evidence.likelihood as likelihood
import vioexplain.core.evidence.scorer as evidence
import vioexplain.core.evidence.unit_models as unit_models
import vioexplain.core.explain.aecx as aecx
import vioexplain.core.explain.assign as assignment
import vioexplain.core.knowledge.footprint as footprint
import vioexplain.core.knowledge.representation as representation
import vioexplain.core.knowledge.twins as twin_module
import vioexplain.core.legacy_aec.apriori as apriori
import vioexplain.core.legacy_aec.models as legacy_models
import vioexplain.core.update.adapter as update_adapter
import vioexplain.core.update.update_graph as update_graph

T, M, ONSET, N_WINDOWS = 32, 8, 16, 4
LENGTH = ONSET + N_WINDOWS * T
STARTS = ONSET + T * np.arange(N_WINDOWS)
EVENTS = (1, 2, 3)
CAPTURE = {}


def clean(value):
    """非有限数转字符串，确保浏览器 JSON.parse 与严格 JSON 兼容。"""
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    if dataclasses.is_dataclass(value):
        return clean(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [clean(v) for v in value]
    return value


@dataclasses.dataclass
class Windows:
    values: np.ndarray
    events: list
    runs: np.ndarray
    starts: np.ndarray

    def positions(self):
        return (self.starts - ONSET) // T


def make_split(n_runs, seed, include_unknown=False):
    """独立随机种子生成 AR(1) 工程教学信号，效应参照仓库 test_method.py。"""
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=(n_runs, LENGTH, M))
    base = np.zeros_like(noise)
    for t in range(LENGTH):
        base[:, t] = noise[:, t] + (0.5 * base[:, t - 1] if t else 0)
    base[:, :, 1] = 0.9 * base[:, :, 0] + 0.3 * noise[:, :, 1]
    arrays = {0: base.astype(np.float32)}
    for event in EVENTS + ((9,) if include_unknown else ()):
        effect = np.zeros_like(base)
        if event == 1:
            effect[:, ONSET:, 0], effect[:, ONSET:, 1] = 3, 2
        elif event == 2:
            effect[:, ONSET:, 3:5] = rng.normal(0, 2.5, (n_runs, LENGTH - ONSET, 2))
        elif event == 3:
            effect[:, ONSET:, 6] = 0.15 * np.arange(LENGTH - ONSET)[None, :]
        else:
            effect[:, ONSET:, 7] = 4
        arrays[event] = (base + effect).astype(np.float32)
    return twin_module.ArrayTwins(arrays, np.arange(1, n_runs + 1), T)


def windows(twins, event_sets):
    values, events, runs, starts = [], [], [], []
    for chosen in event_sets:
        for run in twins.run_ids:
            run_vector = np.full(N_WINDOWS, run)
            values.append(twins.combo(tuple(chosen), run_vector, STARTS))
            events.extend([frozenset(chosen)] * N_WINDOWS)
            runs.extend(run_vector)
            starts.extend(STARTS)
    return Windows(np.concatenate(values), events, np.asarray(runs), np.asarray(starts))


def capture_bank(*args, **kwargs):
    out = ORIGINAL_BANK(*args, **kwargs)
    CAPTURE["bank"] = out
    return out


def capture_training(*args, **kwargs):
    out = ORIGINAL_TRAINING(*args, **kwargs)
    CAPTURE["training_input"] = [v.copy() for v in args[:3]]
    CAPTURE["training_output"] = out
    return out


def capture_threshold(*args, **kwargs):
    out = ORIGINAL_THRESHOLD(*args, **kwargs)
    bound = inspect.signature(ORIGINAL_THRESHOLD).bind(*args, **kwargs)
    bound.apply_defaults()
    data = bound.arguments
    rows = calibration.calibration_rows(data["groups"], len(data["values"]),
                                        data["one_per_run"], data["seed"])
    CAPTURE.setdefault("thresholds", []).append({
        "input_values": data["values"], "groups": data["groups"],
        "strata": data["strata"], "selected_rows": rows,
        "selected_values": np.asarray(data["values"])[rows],
        "sorted_selected_values": np.sort(np.asarray(data["values"])[rows]),
        "rank": calibration.conformal_rank(len(rows), data["alpha"]),
        "result": out.to_dict(),
    })
    return out


ORIGINAL_BANK = api.build_twin_bank
ORIGINAL_TRAINING = api.consistent_training_set
ORIGINAL_THRESHOLD = api.fit_threshold


class RecordingScorer:
    def __init__(self, fitted, calls):
        self.fitted, self.classes, self.calls = fitted, fitted.classes, calls

    def scores(self, phi):
        out = self.fitted.scores(phi)
        self.calls.append({"operation": "scorer.scores", "phi": phi.copy(), "proba": out.copy()})
        return out


class RecordingFootprint:
    def __init__(self, fitted, calls):
        self.fitted, self.calls = fitted, calls

    def deduct_many(self, phi, events):
        out = self.fitted.deduct_many(phi, events)
        self.calls.append({"operation": "footprint.deduct_many", "events": events.copy(),
                           "input": phi.copy(), "delta": phi - out, "output": out.copy()})
        return out


def window_trace(model, test_twins, test, results, index):
    x = test.values[index:index + 1]
    saved = x.copy()
    run, start = int(test.runs[index]), int(test.starts[index])
    base = test_twins.normal([run], [start])
    phi = model.backend.describe(x)
    cs = model.backend.constraint_set
    v = cs.evaluate(x)
    phi_base = model.backend.describe(base)
    calls = []
    engine = aecx.AECX(RecordingScorer(model.scorer, calls),
                       RecordingFootprint(model.footprint, calls), model.tau0, model.tau1,
                       model.config.k_max, model.config.gate_statistic, model.config.stop_statistic,
                       model.assigner, model.tau_u)
    traced = engine.explain(phi, v.violated(), v.signed, cs.keys.ids)[0]
    actual = results[index]
    assert traced.events == actual.events
    assert traced.assignment == actual.assignment
    assert traced.unknown_flag == actual.unknown_flag
    assert np.array_equal(x, saved), "解释不应修改原窗口"
    quantities = []
    for block in cs.blocks:
        q = block.quantity(x.astype(np.float64), cs.center)[0]
        for position, c_index in enumerate(block.columns):
            c = cs.constraints[int(c_index)]
            z = (q[:, position] - c.mid) / c.half
            quantities.append({"constraint_index": int(c_index), "constraint": c.to_dict(),
                               "offset": c.offset, "quantity": q[:, position], "z": z,
                               "F": np.where(np.abs(z) > 1, z, 0),
                               "positive_key": int(2 * c_index), "negative_key": int(2 * c_index + 1),
                               "signed_degrees": [z.max(), -z.min()],
                               "violated": [bool(z.max() > 1), bool(-z.min() > 1)]})
    llr_rows = []
    for k in np.flatnonzero(v.violated()[0]):
        d = float(v.signed[0, k])
        candidates = []
        for event in model.knowledge.events:
            rep = model.knowledge.representation(event)
            eligible = bool(model.likelihood.candidates(event)[k])
            g = float(model.likelihood.llr(event, np.asarray([k]), np.asarray([d]))[0])
            terms = {}
            if eligible:
                lf = float(model.likelihood._lookup(model.likelihood.event_tables[event][k], np.array([d]))[0])
                l0 = float(model.likelihood._lookup(model.likelihood.normal_table[k], np.array([d]))[0])
                le, lr0 = float(model.likelihood.event_log_rate[event][k]), float(model.likelihood.normal_log_rate[k])
                terms = {"log_event_density": lf, "log_normal_density": l0,
                         "log_event_frequency": le, "log_normal_rate_floored": lr0,
                         "sum": lf - l0 + le - lr0}
                assert abs(terms["sum"] - g) < 1e-7
            candidates.append({"event": event, "in_selected_H": event in traced.events,
                               "in_representation": eligible, "llr": g,
                               "but_for_frequency": rep.frequency[k], "terms": terms})
        llr_rows.append({"key": int(k), "key_id": cs.keys.ids[k], "scope": cs.keys.scopes[k],
                         "multi": bool(cs.keys.n_seq[k] > 1), "degree": d,
                         "candidates": candidates, "owner": traced.assignment[cs.keys.ids[k]]})
    selection = model.aecx.select(phi)
    steps = [{"title": "原始窗口与匹配正常孪生", "kind": "window", "shape": list(x.shape)},
             {"title": "四族约束变成有方向的违反键", "kind": "violations", "shape": list(v.signed.shape)},
             {"title": "保留连续信息的描述子 φ", "kind": "descriptor", "shape": list(phi.shape)}]
    for call in calls:
        if call["operation"] == "scorer.scores":
            steps.append({"title": "真实随机森林评分", "kind": "score", **call})
        else:
            steps.append({"title": "从当前描述子扣除最近选择事件的预测足迹", "kind": "deduct", **call})
    steps.extend([{"title": "在原窗口违反上进行 LLR 指派", "kind": "assignment"},
                  {"title": "求背景残差与 unknown 标志", "kind": "unknown"}])
    record = actual.to_record()
    record.pop("elapsed_ms", None)
    return {"index": index, "run": run, "start": start,
            "injected_events": sorted(test.events[index]), "values": x[0], "normal_twin": base[0],
            "injected_delta": (x - base)[0], "phi": phi[0], "phi_normal_twin": phi_base[0],
            "descriptor_delta": (phi - phi_base)[0], "quantities": quantities,
            "violations": [f.to_dict() for f in v.features(0)],
            "all_signed_degrees": v.signed[0], "all_violated": v.violated()[0],
            "calls": calls, "steps": steps, "assignment_detail": llr_rows,
            "result": record, "selection": {"sets": selection.sets, "proba": selection.proba,
             "gate": selection.gate, "tau1": selection.tau1, "step_max": selection.step_max,
             "step_pick": selection.step_pick},
            "raw_window_unchanged": bool(np.array_equal(x, saved))}


def source_entry(obj):
    lines, first = inspect.getsourcelines(obj)
    path = Path(inspect.getsourcefile(obj)).resolve()
    return {"name": obj.__qualname__, "path": str(path.relative_to(ROOT)),
            "start": first, "end": first + len(lines) - 1, "code": "".join(lines),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def record_update(model, buffer):
    inputs, graphs, visits = [], [], []
    original_adapter, original_graph, original_dfs = api.VioExplain.update, update_graph.build_graph, update_graph.dfsvisit
    original_run_update = update_adapter.run_update

    def capture_adapter(*args, **kwargs):
        inputs.append({"transactions": args[0], "knowledge": args[1],
                       "unexplained": args[2], "explained": args[3], "parameters": kwargs})
        out = original_run_update(*args, **kwargs)
        inputs[-1]["outcome"] = dataclasses.asdict(out)
        return out

    def capture_graph(*args, **kwargs):
        g = original_graph(*args, **kwargs)
        graphs.append({"vertices": [[v.id.name, v.id.feature1, v.id.feature2] for v in g],
                       "edges": [{"from": v.id.name, "to": u.id.name,
                                  "confidence": v.getWeight(u)} for v in g for u in v.getConnection()],
                       "rules": [{"antecedent": sorted(c.name for c in r[0]),
                                  "consequent": sorted(c.name for c in r[1]),
                                  "confidence": r[2]} for r in args[2]]})
        return g

    def capture_dfs(*args, **kwargs):
        node, D, C, B, wait, reasons = args[:6]
        visits.append({"phase": "enter", "key": node.id.name, "is_D": node in D,
                       "is_C": node in C, "waiting": [[v.id.name, w] for v, w in wait],
                       "reason_count": len(reasons)})
        result = original_dfs(*args, **kwargs)
        visits.append({"phase": "exit", "key": node.id.name, "reason_count": len(reasons)})
        return result

    import vioexplain.core.update as update_package
    before = model.knowledge.to_dict()
    scorer_classes = model.scorer.classes.copy()
    with patch.object(update_package, "run_update", capture_adapter), \
            patch.object(update_graph, "build_graph", capture_graph), \
            patch.object(update_graph, "dfsvisit", capture_dfs):
        summary = original_adapter(model, buffer)
    assert np.array_equal(model.scorer.classes, scorer_classes)
    return {"buffer_n": len(buffer), "buffer_events": [r.events for r in buffer],
            "buffer_unknown": [r.unknown_flag for r in buffer], "input_output": inputs,
            "graphs": graphs, "dfs": visits, "summary": summary,
            "before": before, "after": model.knowledge.to_dict(),
            "scorer_classes_before": scorer_classes, "scorer_classes_after": model.scorer.classes,
            "new_event_scoring_trained": False}


def update_micro_demo():
    """人为构造缓冲表，真实运行 Apriori 和 Update 的扩充/新建分支。"""
    x, y, z = ("new_x", 2.0, 4.0, 1), ("known_y", 0.0, 1.0, 1), ("isolated_z", 5.0, 6.0, 1)
    transactions = [[x, y], [x, y], [x, y], [x, y], [z]]
    knowledge = {"A": [y], "B": [y]}
    features = [[update_adapter.to_feature(v) for v in row] for row in transactions]
    frequent, support = apriori.Generate_L(features, k=3, min_support=0.2)
    rules = apriori.Generate_big_rules(frequent, support, min_conf=0.7)
    reasons = [legacy_models.Reason(e, {update_adapter.to_feature(f) for f in rows}) for e, rows in knowledge.items()]
    graph = update_graph.build_graph([update_adapter.to_feature(r) for r in (x, y, z)], reasons, rules)
    result = update_adapter.run_update(transactions, knowledge, [x, z], [y])
    return {"scope": "构造的5行规则教学表，非上面的模型预测缓冲；分支结果由原函数计算。",
            "transactions": transactions, "knowledge_before": knowledge, "unexplained": [x, z],
            "explained": [y], "rules": [{"antecedent": sorted(c.name for c in a),
             "consequent": sorted(c.name for c in b), "confidence": c} for a, b, c in rules],
            "edges": [{"from": v.id.name, "to": u.id.name, "confidence": v.getWeight(u)} for v in graph for u in v.getConnection()],
            "result": dataclasses.asdict(result)}


def stacked_diagnostic(model, x, y, groups, cal, test):
    """相同知识与训练表的轻量 stacked 分支，不称为默认配置完整实验。"""
    small = copy.deepcopy(model)
    small.scorer = evidence.StackedScorer(model.backend.units, max_iter=30, n_folds=3, n_jobs=1).fit(x, y, groups)
    small.recalibrate(cal, scorer="stacked", scorer_params={"max_iter": 30, "n_folds": 3})
    s = small.scorer
    rows = np.asarray([0, 128, 256, 384], dtype=int)
    oof = s.unit_models.oof_logodds()
    features = s._features(oof, x)
    standardized = (features - s.center) / s.scale
    logits = standardized[rows] @ s.stacker.coef_.T + s.stacker.intercept_
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    softmax = exp / exp.sum(axis=1, keepdims=True)
    assert np.allclose(softmax, s.stacker.predict_proba(standardized[rows]))
    chosen = [0, 32, 64, 96, 128, 224, 256]
    results = small.explain(test.values[chosen])
    return {"scope": "真实执行轻量 stacked 分支，max_iter=30、n_folds=3；默认是150和5。没有加载时间序列大模型。",
            "shape_oof_logproba": s.unit_models.oof_log_proba.shape,
            "shape_oof_logodds": oof.shape, "shape_stacker_input": features.shape,
            "folds_by_group": {int(g): int(s.unit_models.folds[np.flatnonzero(groups == g)[0]]) for g in np.unique(groups)},
            "fold_counts": dict(zip(*np.unique(s.unit_models.folds, return_counts=True))),
            "preview_rows": rows, "preview_labels": y[rows],
            "preview_oof_logproba": s.unit_models.oof_log_proba[rows],
            "preview_oof_logodds": oof[rows], "preview_stacker_input": features[rows],
            "center": s.center, "scale": s.scale, "preview_standardized": standardized[rows],
            "coef": s.stacker.coef_, "intercept": s.stacker.intercept_,
            "preview_logits": logits, "preview_softmax": softmax,
            "thresholds": {"tau0": small.tau0.to_dict(), "tau1": small.tau1.to_dict(), "tau_u": small.tau_u.to_dict()},
            "test_indices": chosen,
            "test_results": [{k: v for k, v in r.to_record().items() if k != "elapsed_ms"} for r in results],
            "softmax_recomposed": True}


def main():
    fit_twins = make_split(32, 41)
    cal_twins = make_split(40, 42)
    test_twins = make_split(8, 43, True)
    single_sets = [()] + [(e,) for e in EVENTS]
    train, cal = windows(fit_twins, single_sets), windows(cal_twins, single_sets)
    test_sets = [(), (1,), (2,), (3,), (1, 2), (1, 3), (2, 3), (9,), (1, 9)]
    test = windows(test_twins, test_sets)
    config = api.VioExplainConfig(scorer="joint_rf", scorer_params={"n_estimators": 120}, n_jobs=1, chunk=512)
    backend = api.DetectBackend(detect_config=constraints.DetectConfig(window_length=T),
                                channel_names=[f"x{j}" for j in range(M)])
    model = api.VioExplain(config, backend)
    with patch.object(api, "build_twin_bank", capture_bank), \
            patch.object(api, "consistent_training_set", capture_training), \
            patch.object(api, "fit_threshold", capture_threshold):
        model.fit(train, fit_twins, cal)
    results = model.explain(test)
    cs = backend.constraint_set
    bank = CAPTURE["bank"]
    x0, y0, g0 = CAPTURE["training_input"]
    xt, yt, gt = CAPTURE["training_output"]
    bank_rows = []
    offset = len(y0)
    train_segments = [{"kind": "original", "start": 0, "end": len(y0), "label_counts": dict(zip(*np.unique(y0, return_counts=True)))}]
    for event in bank.events:
        b = bank.twins[event]
        op = model.footprint.operators[event]
        h_rows = []
        for row in (0, 1, 2, 3):
            h_rows.append({"row": row, "run": b.runs[row], "start": b.starts[row],
                           "position": b.positions[row], "partner": b.partners[row],
                           "phi_base": b.phi_base[row], "phi_event": b.phi_event[row],
                           "phi_partner": b.phi_partner[row], "phi_combo": b.phi_combo[row],
                           "target_single": b.phi_event[row] - b.phi_base[row],
                           "target_combo": b.phi_combo[row] - b.phi_partner[row],
                           "event_violated": b.violations["event"][0][row],
                           "normal_violated": b.violations["base"][0][row],
                           "event_degrees": b.violations["event"][1][row],
                           "but_for": representation.but_for_indicator(b.violations["event"][0][:4], b.violations["base"][0][:4])[row]})
        bank_rows.append({"event": event, "n_twins": len(b), "n_paired": b.has_partner.sum(),
                          "support_units": model.knowledge.support(event),
                          "support_columns": model.knowledge.support_columns(event),
                          "sample_rows": h_rows,
                          "ridge_coef_shape": None if op is None else op.coef.shape,
                          "ridge_coef": None if op is None else op.coef,
                          "ridge_intercept": None if op is None else op.intercept,
                          "single_footprint_relative_error": model.footprint.relative_error(b.phi_event, b.phi_base, event),
                          "frequencies": model.knowledge.representation(event).frequency})
        for kind, n, label in [("residual", int(b.has_partner.sum()), event),
                                ("self", len(b) // 3 if op else 0, 0)]:
            train_segments.append({"kind": kind, "source_event": event, "label": label,
                                   "start": offset, "end": offset + n,
                                   "first_phi": xt[offset] if n else None,
                                   "first_group": gt[offset] if n else None})
            offset += n
    assert offset == len(yt)
    samples = []
    metrics = []
    for chosen in test_sets:
        candidates = [i for i, label in enumerate(test.events) if label == frozenset(chosen)]
        exact = [i for i in candidates if results[i].event_set == frozenset(chosen)]
        flagged = [i for i in candidates if results[i].unknown_flag]
        index = (flagged or candidates)[0] if 9 in chosen else (exact or candidates)[0]
        sample = window_trace(model, test_twins, test, results, index)
        sample["selection_rule"] = "首个 unknown=True 窗口，否则组首行" if 9 in chosen else "首个事件集完全正确窗口，否则组首行"
        samples.append(sample)
        metrics.append({"injected": chosen, "n": len(candidates), "exact_set_recovery": len(exact) / len(candidates),
                        "unknown_fraction": len(flagged) / len(candidates),
                        "predicted_sets": {str(s): sum(results[i].events == s for i in candidates)
                                           for s in sorted({results[i].events for i in candidates})}})
    unknown_buffer = [r for i, r in enumerate(results) if test.events[i] == frozenset((9,)) and r.unknown_flag][:12]
    update = record_update(copy.deepcopy(model), unknown_buffer)
    source_objects = [api.VioExplain.fit, api.VioExplain._calibrate, api.VioExplain.explain, api.VioExplain.update,
                      api.DetectBackend, api.VioExplainConfig, constraints.fit_constraints, constraints.select_relations,
                      constraints._learn_bounds, constraints.rolling_variance, constraints.Block.quantity,
                      violations.evaluate, violations.pointwise_degree, descriptors.build_layout,
                      descriptors.window_statistics, descriptors._fill_chunk, representation.but_for_indicator,
                      representation.fit_representation, representation.support_from_effects, representation.fit_knowledge,
                      representation.Knowledge.add_possible, twin_module.build_twin_bank, twin_module.ArrayTwins.combo,
                      footprint.ridge_fit, footprint.Footprint.fit, footprint.Footprint.deduct,
                      evidence.consistent_training_set, evidence.StackedScorer, evidence.JointRFScorer,
                      unit_models.UnitModels, unit_models._fit_unit, unit_models.fold_assignment,
                      aecx.gate_statistic, aecx.stop_statistic, aecx.AECX.select, aecx.AECX.explain,
                      likelihood.DegreeLikelihood, assignment.Assigner._block, assignment.Assigner.assign,
                      calibration.conformal_quantile, calibration.fit_threshold, calibration.Threshold.lookup,
                      update_adapter.run_update, update_graph.build_graph, update_graph.Update, update_graph.dfsvisit]
    payload = {
        "schema_version": 1,
        "scope": "教学合成数据的原代码真实执行，不是 Rieth/TEP 正式实验结果；所有概率来自实际拟合的随机森林，没有预设评分。",
        "provenance": {"script": str(Path(__file__).relative_to(ROOT)), "python": platform.python_version(),
                       "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__,
                       "code_root": "code_v3", "seed_fit": 41, "seed_cal": 42, "seed_test": 43,
                       "model_seed": 0, "stubbed_components": [],
                       "not_executed": ["默认 stacked scorer 150迭代/5折正式配置", "Rieth/TEP 正式实验", "Chronos2/MOMENT/Mantis",
                                        "新事件 scorer 训练（API update 本身没有实现）"]},
        "data": {"T": T, "M": M, "run_length": LENGTH, "onset": ONSET, "starts": STARTS,
                 "channels": cs.channel_names, "events": {0: "正常", 1: "x0 均值 +3 且 x1 均值 +2",
                      2: "x3、x4 附加标准差 2.5 白噪声", 3: "x6 每采样点增加 0.15 的斜坡", 9: "未见事件，x7 均值 +4"},
                 "fit_shape": train.values.shape, "cal_shape": cal.values.shape, "test_shape": test.values.shape,
                 "fit_run_count": 32, "cal_run_count": 40, "test_run_count": 8,
                 "split_note": "三个划分用独立随机种子，run 数字各自从 1 起，不代表跨划分同一轨迹。"},
        "defaults": {"method": api.VioExplainConfig().to_dict(), "detect": constraints.DetectConfig().to_dict()},
        "actual_config": {"method": config.to_dict(), "detect": cs.config.to_dict()},
        "fit_summary": model.describe_fit(), "constraints": cs.describe(),
        "layout": descriptors.build_layout(cs).to_dict(),
        "key_table": [cs.keys.describe(k) for k in range(cs.n_keys)],
        "descriptor_normalizers": cs.descriptor_model.to_dict(),
        "knowledge": model.knowledge.to_dict(), "bank": bank_rows,
        "training": {"original_shape": x0.shape, "expanded_shape": xt.shape,
                     "classes": model.scorer.classes, "label_counts": dict(zip(*np.unique(yt, return_counts=True))),
                     "segments": train_segments, "group_count": len(np.unique(gt)),
                     "joint_rf_groups_note": "consistent_training_set 保留 run 分组，但 JointRFScorer.fit 忽略 groups；默认 stacked 会使用分组交叉拟合。"},
        "calibration": {name: value for name, value in zip(("tau0", "tau1", "tau_u"), CAPTURE["thresholds"])},
        "samples": samples, "synthetic_metrics": metrics, "update": update,
        "update_micro_demo": update_micro_demo(),
        "stacked_diagnostic": stacked_diagnostic(model, xt, yt, gt, cal, test),
        "sources": [source_entry(obj) for obj in source_objects],
        "verification": {"tracer_matches_actual_api": True, "raw_windows_unchanged": True,
                         "training_segment_counts_match": True, "llr_terms_recompose": True,
                         "update_keeps_scorer_classes": True},
    }
    out = Path(__file__).with_name("vioexplain-runtime.json")
    out.write_text(json.dumps(clean(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(out), "bytes": out.stat().st_size,
                      "constraints": cs.n_constraints, "keys": cs.n_keys, "descriptor_dim": x0.shape[1],
                      "training_shape": xt.shape, "metrics": metrics,
                      "update_summary": update["summary"]}, default=clean, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
