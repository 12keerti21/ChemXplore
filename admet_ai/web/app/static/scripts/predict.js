$(function () {
    const config = window.CHEMXPLORE || {};

    // Keep the session and stored predictions alive while the page is open
    if (config.heartbeatSeconds > 0) {
        setInterval(function () {
            fetch("/heartbeat", {method: "POST"}).catch(function () {});
        }, config.heartbeatSeconds * 1000);
    }

    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
        new bootstrap.Tooltip(element, {container: "body"});
    });

    $(document).on("click", ".collapse-button", function () {
        $(this).find(".arrow").first().toggleClass("arrow-up");
    });

    $(window).on("scroll", function () {
        $(".navbar").toggleClass("scrolled", $(this).scrollTop() > 50);
    });

    // Input type switching. Only the visible input is required, otherwise the browser blocks submit.
    const inputForms = {
        text: {form: "#text-input-form", field: "#text-smiles-input"},
        example: {form: "#text-input-form", field: "#text-smiles-input"},
        name: {form: "#name-input-form", field: "#text-names-input"},
        file: {form: "#file-input-form", field: "#file-smiles-input"},
        draw: {form: "#draw-input-form", field: null},
    };
    const exampleSmiles = [
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "CC(=O)Oc1ccccc1C(=O)O",
        "CN1C=NC2=C1C(=O)N(C)C(=O)N2C",
        "O(c1ccc(cc1)CCOC)CC(O)CNC(C)C",
    ].join("\n");

    function resizeJSME() {
        const container = document.getElementById("jsme_container");
        if (window.jsmeApplet && container) {
            jsmeApplet.setSize(container.offsetWidth + "px", "400px");
        }
    }

    function showInput(type) {
        $.each(inputForms, function (_, input) {
            $(input.form).hide();
            if (input.field) {
                $(input.field).prop("required", false);
            }
        });

        const selected = inputForms[type];
        $(selected.form).show();
        if (selected.field) {
            $(selected.field).prop("required", true);
        }

        if (type === "example") {
            $("#text-smiles-input").val(exampleSmiles);
        }
        if (type === "draw") {
            resizeJSME();
        }
    }

    $('input[name="input-type"]').on("change", function () {
        showInput($(this).val());
    });
    showInput($('input[name="input-type"]:checked').val() || "text");
    $(window).on("resize", resizeJSME);

    $("#molecule-form").on("submit", function (event) {
        const type = $('input[name="input-type"]:checked').val();
        // The server treats the example as typed SMILES
        if (type === "example") {
            $("#text-radio").prop("checked", true);
        }
        if (type === "draw") {
            const smiles = window.jsmeApplet ? jsmeApplet.smiles() : "";
            if (!smiles) {
                event.preventDefault();
                alert("Draw a molecule first.");
                return;
            }
            $("#draw-smiles-input").val(smiles);
        }

        $("#predict-button").addClass("loading");
        $("#spinner-overlay").css("display", "flex");
    });

    // Reset the spinner when the browser restores the page from its back/forward cache
    $(window).on("pageshow", function () {
        $("#spinner-overlay").hide();
        $("#predict-button").removeClass("loading");
    });

    // ATC code search and selection
    $("#atc-selection").on("input", function () {
        const value = $(this).val().toLowerCase();
        $(".atc-item").each(function () {
            $(this).toggle($(this).text().toLowerCase().includes(value));
        });
    });

    $(".atc-item").on("click", function () {
        const atcCode = $(this).text().trim();
        $.ajax({
            url: "/set_atc_code?atc_code=" + encodeURIComponent(atcCode),
            type: "POST",
            dataType: "json",
        }).done(function (response) {
            $("#selected-atc-code").text(response.atc_code);
            $("#drugbank-size").text(response.drugbank_size_string);
            if ($("#results").length) {
                $("#atc-rerun-note").show();
            }
        }).fail(function () {
            alert("Could not change the ATC code. Please try again.");
        });
    });

    // DrugBank plot axes
    $(".drugbank-axis-select").on("change", function () {
        const task = $(this).val();
        if (!task) {
            return;
        }

        const plot = $("#drugbank-plot-inner");
        plot.css("opacity", 0.4);
        $.getJSON("/drugbank_plot", {[$(this).data("axis") + "_task"]: task})
            .done(function (response) {
                plot.html(response.svg);
            })
            .fail(function () {
                alert("Could not update the plot. Your results may have expired, so try predicting again.");
            })
            .always(function () {
                plot.css("opacity", 1);
            });
    });
});
