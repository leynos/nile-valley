"""Exception hierarchy for nile-valley-infra-k8s utilities.

These exceptions provide a domain-specific error surface for the shared action
helpers so callers can catch a single base error when appropriate.

Examples
--------
>>> raise TofuCommandError("tofu output failed")
"""

from __future__ import annotations


class InfraK8sError(Exception):
    """Base error for nile-valley-infra-k8s orchestration helpers.

    Parameters
    ----------
    message
        Human-readable error message describing the failure.

    Examples
    --------
    >>> raise InfraK8sError("unexpected infra failure")
    """


class TofuCommandError(InfraK8sError):
    """Raised when an OpenTofu command fails.

    Parameters
    ----------
    message
        Human-readable error message describing the OpenTofu failure.

    Examples
    --------
    >>> raise TofuCommandError("tofu apply failed: exit status 1")
    """
