"""
Staff only: the quality dashboard and the evidence for one recipe.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

import json
from datetime import timedelta
from collections import Counter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


from .models import (
    Recipe,
)





# Staff view: monitors AI recipe validation quality, risk, trends and review priorities.
@login_required
def quality_dashboard_view(request):
    """
    Staff-only CulinaAI quality dashboard.

    Upgraded admin analytics version:
    - Summary metrics
    - Validation score analytics
    - Risk analytics
    - Validation health analytics
    - Recipe generation trend
    - Top cuisine and meal type analytics
    - Staff review priority overview
    - Searchable and filterable validation records
    """

    # Important: quality dashboard is restricted to staff/admin users only.
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(
            request,
            "That page is only for site admins.",
        )
        return redirect("home")

    # Important: dashboard analyses saved AI-generated recipes only.
    recipes = Recipe.objects.filter(
        is_ai_generated=True,
        is_saved=True,
    )

    validated_recipes = recipes.filter(
        quality_score__isnull=False,
    )

    total_ai_recipes = recipes.count()
    validated_count = validated_recipes.count()
    unvalidated_count = total_ai_recipes - validated_count

    scores = list(
        validated_recipes.values_list(
            "quality_score",
            flat=True,
        )
    )

    if scores:
        average_score = round(sum(scores) / len(scores), 1)
        highest_score = max(scores)
        lowest_score = min(scores)
    else:
        average_score = 0
        highest_score = 0
        lowest_score = 0

    excellent_count = validated_recipes.filter(
        quality_score__gte=85,
    ).count()

    verified_count = validated_recipes.filter(
        quality_score__gte=70,
        quality_score__lt=85,
    ).count()

    moderate_count = validated_recipes.filter(
        quality_score__gte=50,
        quality_score__lt=70,
    ).count()

    needs_review_count = validated_recipes.filter(
        quality_score__lt=50,
    ).count()

    low_risk_count = validated_recipes.filter(
        validation_risk_level__icontains="low",
    ).count()

    medium_risk_count = validated_recipes.filter(
        validation_risk_level__icontains="medium",
    ).count()

    high_risk_count = validated_recipes.filter(
        validation_risk_level__icontains="high",
    ).count()

    unknown_risk_count = max(
        total_ai_recipes - low_risk_count - medium_risk_count - high_risk_count,
        0,
    )

    first_attempt_count = validated_recipes.filter(
        validation_attempts__lte=1,
    ).count()

    corrected_count = validated_recipes.filter(
        validation_attempts__gt=1,
    ).count()

    attempt_values = list(
        validated_recipes.values_list(
            "validation_attempts",
            flat=True,
        )
    )

    if attempt_values:
        average_attempts = round(sum(attempt_values) / len(attempt_values), 1)
    else:
        average_attempts = 0

    def percentage(part, total):
        if not total:
            return 0
        return round((part / total) * 100, 1)

    validation_coverage_rate = percentage(validated_count, total_ai_recipes)
    unvalidated_rate = percentage(unvalidated_count, total_ai_recipes)
    first_attempt_rate = percentage(first_attempt_count, validated_count)
    regeneration_rate = percentage(corrected_count, validated_count)

    fallback_count = 0
    issue_counter = Counter()

    for recipe in validated_recipes:
        report = recipe.validation_report or {}
        attempt_history = recipe.validation_attempt_history or []

        combined_text = (
            f"{recipe.validation_status} "
            f"{recipe.validation_badge} "
            f"{report} "
            f"{attempt_history}"
        ).lower()

        if "fallback" in combined_text:
            fallback_count += 1

        if recipe.quality_score is not None and recipe.quality_score < 85:
            issue_counter["Score below excellent threshold"] += 1

        if recipe.validation_risk_level:
            risk_text = recipe.validation_risk_level.lower()

            if "medium" in risk_text:
                issue_counter["Medium risk validation result"] += 1

            if "high" in risk_text:
                issue_counter["High risk validation result"] += 1

        if isinstance(report, dict):
            possible_check_lists = [
                report.get("checks"),
                report.get("criteria"),
                report.get("validation_checks"),
                report.get("check_results"),
            ]

            for check_list in possible_check_lists:
                if not isinstance(check_list, list):
                    continue

                for check in check_list:
                    if not isinstance(check, dict):
                        continue

                    check_name = (
                        check.get("name")
                        or check.get("category")
                        or check.get("title")
                        or check.get("criterion")
                        or "Validation check"
                    )

                    check_status = str(
                        check.get("status")
                        or check.get("result")
                        or ""
                    ).lower()

                    check_passed = check.get("passed")

                    if (
                        check_passed is False
                        or "fail" in check_status
                        or "warning" in check_status
                        or "review" in check_status
                    ):
                        issue_counter[str(check_name)] += 1

            warning_items = report.get("warnings") or report.get("issues") or []

            if isinstance(warning_items, list):
                for warning in warning_items:
                    if isinstance(warning, str) and warning.strip():
                        issue_counter[warning.strip()] += 1

    if unvalidated_count:
        issue_counter["Older recipes without stored validation evidence"] += unvalidated_count

    common_issues = [
        {
            "label": label,
            "count": count,
        }
        for label, count in issue_counter.most_common(5)
    ]

    staff_review_queryset = recipes.filter(
        Q(quality_score__lt=85)
        | Q(quality_score__isnull=True)
        | Q(validation_risk_level__icontains="medium")
        | Q(validation_risk_level__icontains="high")
    )

    staff_review_recipes = (
        staff_review_queryset
        .select_related(
            "user",
            "cuisine",
            "meal_type",
        )
        .order_by("-created_at")[:6]
    )

    staff_review_count = staff_review_queryset.count()

    high_priority_count = recipes.filter(
        Q(quality_score__lt=50)
        | Q(validation_risk_level__icontains="high")
    ).count()

    medium_priority_count = recipes.filter(
        Q(quality_score__gte=50, quality_score__lt=70)
        | Q(validation_risk_level__icontains="medium")
    ).exclude(
        Q(quality_score__lt=50)
        | Q(validation_risk_level__icontains="high")
    ).count()

    low_priority_count = max(
        staff_review_count - high_priority_count - medium_priority_count,
        0,
    )

    if average_score >= 85 and high_risk_count == 0:
        quality_health_label = "Excellent"
        quality_health_text = (
            "The validation system is performing strongly with high average quality "
            "and no high-risk records."
        )
    elif average_score >= 70:
        quality_health_label = "Stable"
        quality_health_text = (
            "The validation system is generally stable, but some records may still "
            "require staff review."
        )
    else:
        quality_health_label = "Needs Review"
        quality_health_text = (
            "The validation system has lower scoring records, so staff review is recommended."
        )

    # Chart data: score distribution.
    score_distribution_chart_data = {
        "labels": [
            "Excellent",
            "Verified",
            "Moderate",
            "Needs Review",
        ],
        "values": [
            excellent_count,
            verified_count,
            moderate_count,
            needs_review_count,
        ],
    }

    # Chart data: risk levels.
    risk_level_chart_data = {
        "labels": [
            "Low Risk",
            "Medium Risk",
            "High Risk",
            "Unknown",
        ],
        "values": [
            low_risk_count,
            medium_risk_count,
            high_risk_count,
            unknown_risk_count,
        ],
    }

    # Chart data: validation health.
    validation_health_chart_data = {
        "labels": [
            "Validated",
            "Unvalidated",
            "First Attempt",
            "Regenerated",
            "Fallback Used",
        ],
        "values": [
            validated_count,
            unvalidated_count,
            first_attempt_count,
            corrected_count,
            fallback_count,
        ],
    }

    # Chart data: last 7 days AI recipe generation trend.
    today = timezone.localdate()
    trend_start_date = today - timedelta(days=6)

    trend_labels = []
    trend_values = []

    for day_offset in range(7):
        current_day = trend_start_date + timedelta(days=day_offset)

        trend_labels.append(current_day.strftime("%d %b"))

        trend_values.append(
            recipes.filter(
                created_at__date=current_day,
            ).count()
        )

    recipe_trend_chart_data = {
        "labels": trend_labels,
        "values": trend_values,
    }

    # Chart data: top cuisines.
    top_cuisine_rows = (
        recipes.exclude(cuisine__isnull=True)
        .values("cuisine__name")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )

    top_cuisine_chart_data = {
        "labels": [
            row["cuisine__name"] or "Not specified"
            for row in top_cuisine_rows
        ],
        "values": [
            row["total"]
            for row in top_cuisine_rows
        ],
    }

    # Chart data: top meal types.
    top_meal_type_rows = (
        recipes.exclude(meal_type__isnull=True)
        .values("meal_type__name")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )

    top_meal_type_chart_data = {
        "labels": [
            row["meal_type__name"] or "Not specified"
            for row in top_meal_type_rows
        ],
        "values": [
            row["total"]
            for row in top_meal_type_rows
        ],
    }

    # Chart data: common issues.
    common_issue_chart_data = {
        "labels": [
            issue["label"][:42]
            for issue in common_issues
        ],
        "values": [
            issue["count"]
            for issue in common_issues
        ],
    }

    # Staff priority data.
    staff_priority_chart_data = {
        "labels": [
            "High Priority",
            "Medium Priority",
            "Low Priority",
        ],
        "values": [
            high_priority_count,
            medium_priority_count,
            low_priority_count,
        ],
    }

    # Stage 3C filter controls for the recipe records table.
    search_query = request.GET.get("q", "").strip()
    validation_filter = request.GET.get("validation", "all")
    risk_filter = request.GET.get("risk", "all")
    sort_filter = request.GET.get("sort", "latest")

    filtered_recipes = recipes.select_related(
        "user",
        "cuisine",
        "meal_type",
    )

    if search_query:
        filtered_recipes = filtered_recipes.filter(
            Q(title__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(cuisine__name__icontains=search_query)
            | Q(meal_type__name__icontains=search_query)
        )

    if validation_filter == "validated":
        filtered_recipes = filtered_recipes.filter(
            quality_score__isnull=False,
        )
    elif validation_filter == "unvalidated":
        filtered_recipes = filtered_recipes.filter(
            quality_score__isnull=True,
        )
    elif validation_filter == "excellent":
        filtered_recipes = filtered_recipes.filter(
            quality_score__gte=85,
        )
    elif validation_filter == "below_excellent":
        filtered_recipes = filtered_recipes.filter(
            Q(quality_score__lt=85) | Q(quality_score__isnull=True)
        )
    elif validation_filter == "needs_review":
        filtered_recipes = filtered_recipes.filter(
            Q(quality_score__lt=70)
            | Q(quality_score__isnull=True)
            | Q(validation_risk_level__icontains="medium")
            | Q(validation_risk_level__icontains="high")
        )

    if risk_filter == "low":
        filtered_recipes = filtered_recipes.filter(
            validation_risk_level__icontains="low",
        )
    elif risk_filter == "medium":
        filtered_recipes = filtered_recipes.filter(
            validation_risk_level__icontains="medium",
        )
    elif risk_filter == "high":
        filtered_recipes = filtered_recipes.filter(
            validation_risk_level__icontains="high",
        )
    elif risk_filter == "unknown":
        filtered_recipes = filtered_recipes.filter(
            Q(validation_risk_level__isnull=True)
            | Q(validation_risk_level="")
        )

    if sort_filter == "oldest":
        filtered_recipes = filtered_recipes.order_by("created_at")
    elif sort_filter == "score_high":
        filtered_recipes = filtered_recipes.order_by("-quality_score", "-created_at")
    elif sort_filter == "score_low":
        filtered_recipes = filtered_recipes.order_by("quality_score", "-created_at")
    else:
        filtered_recipes = filtered_recipes.order_by("-created_at")

    filtered_recipe_count = filtered_recipes.count()
    filtered_recipes = filtered_recipes[:30]

    context = {
        "total_ai_recipes": total_ai_recipes,
        "validated_count": validated_count,
        "unvalidated_count": unvalidated_count,
        "average_score": average_score,
        "excellent_count": excellent_count,
        "verified_count": verified_count,
        "moderate_count": moderate_count,
        "needs_review_count": needs_review_count,
        "low_risk_count": low_risk_count,
        "medium_risk_count": medium_risk_count,
        "high_risk_count": high_risk_count,
        "unknown_risk_count": unknown_risk_count,
        "first_attempt_count": first_attempt_count,
        "corrected_count": corrected_count,
        "recent_recipes": filtered_recipes,
        "filtered_recipe_count": filtered_recipe_count,
        "search_query": search_query,
        "validation_filter": validation_filter,
        "risk_filter": risk_filter,
        "sort_filter": sort_filter,
        "validation_coverage_rate": validation_coverage_rate,
        "unvalidated_rate": unvalidated_rate,
        "first_attempt_rate": first_attempt_rate,
        "regeneration_rate": regeneration_rate,
        "fallback_count": fallback_count,
        "average_attempts": average_attempts,
        "highest_score": highest_score,
        "lowest_score": lowest_score,
        "staff_review_recipes": staff_review_recipes,
        "staff_review_count": staff_review_count,
        "high_priority_count": high_priority_count,
        "medium_priority_count": medium_priority_count,
        "low_priority_count": low_priority_count,
        "common_issues": common_issues,
        "quality_health_label": quality_health_label,
        "quality_health_text": quality_health_text,

        # Chart.js JSON data.
        "score_distribution_chart_data": json.dumps(score_distribution_chart_data),
        "risk_level_chart_data": json.dumps(risk_level_chart_data),
        "validation_health_chart_data": json.dumps(validation_health_chart_data),
        "recipe_trend_chart_data": json.dumps(recipe_trend_chart_data),
        "top_cuisine_chart_data": json.dumps(top_cuisine_chart_data),
        "top_meal_type_chart_data": json.dumps(top_meal_type_chart_data),
        "common_issue_chart_data": json.dumps(common_issue_chart_data),
        "staff_priority_chart_data": json.dumps(staff_priority_chart_data),
    }

    return render(request, "recipes/quality_dashboard.html", context)


# Staff view: shows stored AI prompt, response, validation report and attempt history evidence.
@login_required
def quality_recipe_evidence_view(request, recipe_id):
    """
    Staff-only validation evidence detail page.

    Allows staff/admin users to inspect human-readable validation evidence,
    stored validation report, attempt history and saved AI recipe output.
    """

    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(
            request,
            "That page is only for site admins.",
        )
        return redirect("home")

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "user",
            "cuisine",
            "meal_type",
        ),
        id=recipe_id,
        is_ai_generated=True,
        is_saved=True,
    )

    validation_report = recipe.validation_report or {}
    validation_attempt_history = recipe.validation_attempt_history or []

    # Important: JSON evidence is formatted for readable staff review.
    validation_report_pretty = json.dumps(
        validation_report,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    validation_attempt_history_pretty = json.dumps(
        validation_attempt_history,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    # Main saved AI output.
    # Your Recipe model stores the full AI output in ai_response.
    recipe_content = recipe.ai_response.strip() if recipe.ai_response else ""

    # Fallback for older/manual records where ai_response may be empty.
    if not recipe_content:
        fallback_parts = []

        if recipe.description:
            fallback_parts.append(f"Description:\n{recipe.description}")

        if recipe.ingredients_text:
            fallback_parts.append(f"Ingredients:\n{recipe.ingredients_text}")

        if recipe.instructions_text:
            fallback_parts.append(f"Instructions:\n{recipe.instructions_text}")

        recipe_content = "\n\n".join(fallback_parts)

    def get_first_existing(check_data, possible_keys, default=""):
        for key in possible_keys:
            value = check_data.get(key)

            if value is not None and value != "":
                return value

        return default

    def build_score_text(check_data):
        awarded = get_first_existing(
            check_data,
            [
                "score_awarded",
                "awarded_score",
                "points_awarded",
                "score",
                "points",
            ],
            None,
        )

        maximum = get_first_existing(
            check_data,
            [
                "max_score",
                "maximum_score",
                "max_points",
                "total_points",
                "out_of",
            ],
            None,
        )

        if awarded is not None and maximum is not None:
            return f"{awarded}/{maximum}"

        if awarded is not None:
            return str(awarded)

        return ""

    def build_readable_check(check_data, fallback_name="Validation check"):
        check_name = get_first_existing(
            check_data,
            [
                "name",
                "category",
                "title",
                "criterion",
                "check",
                "label",
            ],
            fallback_name,
        )

        message = get_first_existing(
            check_data,
            [
                "message",
                "detail",
                "details",
                "explanation",
                "reason",
                "note",
                "notes",
                "feedback",
            ],
            "No extra explanation stored for this check.",
        )

        raw_status = str(
            get_first_existing(
                check_data,
                [
                    "status",
                    "result",
                    "outcome",
                    "state",
                ],
                "",
            )
        ).lower()

        passed = get_first_existing(
            check_data,
            [
                "passed",
                "is_passed",
                "success",
                "valid",
            ],
            None,
        )

        hard_fail = get_first_existing(
            check_data,
            [
                "hard_fail",
                "critical_fail",
                "failed",
            ],
            False,
        )

        if passed is True or raw_status in ["passed", "pass", "success", "verified"]:
            status_label = "Passed"
            css_class = "check-passed"
            icon = "icon-circle-check"
        elif hard_fail is True or passed is False or "fail" in raw_status:
            status_label = "Failed"
            css_class = "check-failed"
            icon = "icon-circle-x"
        elif "warning" in raw_status or "review" in raw_status or "moderate" in raw_status:
            status_label = "Warning"
            css_class = "check-warning"
            icon = "icon-triangle-alert"
        else:
            status_label = "Recorded"
            css_class = "check-info"
            icon = "icon-info"

        return {
            "label": str(check_name).replace("_", " ").title(),
            "message": str(message),
            "score_text": build_score_text(check_data),
            "status_label": status_label,
            "css_class": css_class,
            "icon": icon,
        }

    readable_validation_checks = []

    if isinstance(validation_report, dict):
        possible_check_lists = [
            validation_report.get("checks"),
            validation_report.get("criteria"),
            validation_report.get("validation_checks"),
            validation_report.get("check_results"),
            validation_report.get("score_breakdown"),
            validation_report.get("criteria_results"),
            validation_report.get("results"),
        ]

        for check_list in possible_check_lists:
            if isinstance(check_list, list):
                for check in check_list:
                    if isinstance(check, dict):
                        readable_validation_checks.append(
                            build_readable_check(check)
                        )

            elif isinstance(check_list, dict):
                for key, value in check_list.items():
                    if isinstance(value, dict):
                        readable_validation_checks.append(
                            build_readable_check(value, fallback_name=key)
                        )
                    else:
                        readable_validation_checks.append(
                            {
                                "label": str(key).replace("_", " ").title(),
                                "message": f"Stored value: {value}",
                                "score_text": "",
                                "status_label": "Recorded",
                                "css_class": "check-info",
                                "icon": "icon-info",
                            }
                        )

        warning_items = validation_report.get("warnings") or validation_report.get("issues") or []

        if isinstance(warning_items, list):
            for warning in warning_items:
                if warning:
                    readable_validation_checks.append(
                        {
                            "label": "Validation Warning",
                            "message": str(warning),
                            "score_text": "",
                            "status_label": "Warning",
                            "css_class": "check-warning",
                            "icon": "icon-triangle-alert",
                        }
                    )

    # Fallback readable evidence if no detailed check list exists in JSON.
    if not readable_validation_checks:
        readable_validation_checks = [
            {
                "label": "Overall Quality Score",
                "message": "Final stored quality score produced by the CulinaAI validation engine.",
                "score_text": f"{recipe.quality_score}/100" if recipe.quality_score is not None else "Not stored",
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "icon-layout-dashboard",
            },
            {
                "label": "Validation Status",
                "message": recipe.validation_status or "No validation status was stored for this recipe.",
                "score_text": "",
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "icon-badge-check",
            },
            {
                "label": "Risk Level",
                "message": recipe.validation_risk_level or "No risk level was stored for this recipe.",
                "score_text": "",
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "icon-shield-alert",
            },
            {
                "label": "Validation Attempts",
                "message": "Number of generation, correction or fallback attempts stored for this recipe.",
                "score_text": str(recipe.validation_attempts or 0),
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "icon-refresh-cw",
            },
        ]

    context = {
        "recipe": recipe,
        "recipe_content": recipe_content,
        "readable_validation_checks": readable_validation_checks,
        "validation_report_pretty": validation_report_pretty,
        "validation_attempt_history_pretty": validation_attempt_history_pretty,
    }

    return render(request, "recipes/quality_recipe_evidence.html", context)
