"""
Tests for the CapitalProvider module.

Tests cover:
- ConfigCapitalProvider for PAPER mode
- LiveCapitalProvider for LIVE mode with Kite API mocking
- Factory function create_capital_provider
"""

import pytest
from unittest.mock import MagicMock, patch
from core.capital_provider import (
    CapitalProvider,
    ConfigCapitalProvider,
    LiveCapitalProvider,
    create_capital_provider,
)


class TestConfigCapitalProvider:
    """Tests for ConfigCapitalProvider (PAPER mode)."""

    def test_init_with_capital(self):
        """Test initialization with capital value."""
        provider = ConfigCapitalProvider(500000.0)
        assert provider.get_available_capital() == 500000.0

    def test_refresh_returns_same_capital(self):
        """Test refresh returns same configured capital."""
        provider = ConfigCapitalProvider(250000.0)
        assert provider.refresh() == 250000.0
        assert provider.get_available_capital() == 250000.0

    def test_set_capital_updates_value(self):
        """Test set_capital updates the stored capital."""
        provider = ConfigCapitalProvider(100000.0)
        assert provider.get_available_capital() == 100000.0
        
        provider.set_capital(200000.0)
        assert provider.get_available_capital() == 200000.0


class TestLiveCapitalProvider:
    """Tests for LiveCapitalProvider (LIVE mode)."""

    def test_init_builds_client_from_env(self):
        """Test initialization builds Kite client from env."""
        mock_kite = MagicMock()
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 100000.0}
            
            provider = LiveCapitalProvider(
                fallback_capital=100000.0,
                cache_ttl_seconds=30.0,
            )
            
            assert provider._fallback_capital == 100000.0
            assert provider._cache_ttl == 30.0
            mock_make.assert_called_once()

    def test_refresh_fetches_from_kite_api(self):
        """Test refresh fetches capital from Kite margins API."""
        mock_kite = MagicMock()
        
        # Mock margins("equity") response
        mock_margins_response = {
            "equity": {
                "net": 450000.0,
                "available": {"cash": 400000.0},
                "utilised": {"span": 50000.0},
            }
        }
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 100000.0}  # constructor sanity check
            
            with patch("core.kite_http.kite_request") as mock_kite_request:
                mock_kite_request.return_value = mock_margins_response
                
                provider = LiveCapitalProvider(
                    fallback_capital=100000.0,
                )
                
                capital = provider.refresh()
                
                # Should return the "net" value from response
                assert capital == 450000.0
                mock_kite_request.assert_called_once_with(mock_kite.margins, "equity")

    def test_refresh_uses_fallback_on_api_error(self):
        """Test refresh uses fallback capital on API error."""
        mock_kite = MagicMock()
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.side_effect = Exception("API error")
            
            with patch("core.kite_http.kite_request") as mock_kite_request:
                mock_kite_request.side_effect = Exception("API error")
                
                provider = LiveCapitalProvider(
                    fallback_capital=100000.0,
                )
                
                capital = provider.refresh()
                
                assert capital == 100000.0

    def test_get_available_capital_uses_cache(self):
        """Test get_available_capital uses cached value within TTL."""
        mock_kite = MagicMock()
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 100000.0}  # constructor sanity check
            
            with patch("core.kite_http.kite_request") as mock_kite_request:
                mock_kite_request.return_value = {"net": 500000.0}
                
                provider = LiveCapitalProvider(
                    fallback_capital=100000.0,
                    cache_ttl_seconds=60.0,
                )
                
                # First call should fetch from API
                capital1 = provider.get_available_capital()
                assert capital1 == 500000.0
                
                # Second call should use cache (not call API again)
                capital2 = provider.get_available_capital()
                assert capital2 == 500000.0
                
                # API should only be called once
                assert mock_kite_request.call_count == 1

    def test_invalidate_cache_forces_refresh(self):
        """Test invalidate_cache forces next get to fetch fresh data."""
        mock_kite = MagicMock()
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 100000.0}  # constructor sanity check
            
            with patch("core.kite_http.kite_request") as mock_kite_request:
                mock_kite_request.return_value = {"net": 500000.0}
                
                provider = LiveCapitalProvider(
                    fallback_capital=100000.0,
                    cache_ttl_seconds=60.0,
                )
                
                # First call
                provider.get_available_capital()
                assert mock_kite_request.call_count == 1
                
                # Invalidate cache
                provider.invalidate_cache()
                
                # Next call should fetch fresh
                mock_kite_request.return_value = {"net": 550000.0}
                capital = provider.get_available_capital()
                
                assert capital == 550000.0
                assert mock_kite_request.call_count == 2

    def test_refresh_fallback_to_cash_if_net_zero(self):
        """Test refresh falls back to cash if net is zero."""
        mock_kite = MagicMock()
        
        mock_margins_response = {
            "equity": {
                "net": 0.0,
                "available": {"cash": 300000.0},
            }
        }
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 100000.0}  # constructor sanity check
            
            with patch("core.kite_http.kite_request") as mock_kite_request:
                mock_kite_request.return_value = mock_margins_response
                
                provider = LiveCapitalProvider(
                    fallback_capital=100000.0,
                )
                
                capital = provider.refresh()
                
                # Should return cash value since net is zero
                assert capital == 300000.0

    def test_get_client_returns_kite(self):
        """Test get_client returns the Kite client."""
        mock_kite = MagicMock()
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 100000.0}
            
            provider = LiveCapitalProvider(fallback_capital=100000.0)
            
            assert provider.get_client() is mock_kite


class TestCreateCapitalProvider:
    """Tests for the factory function create_capital_provider."""

    def test_create_paper_mode_provider(self):
        """Test creating provider for PAPER mode."""
        provider = create_capital_provider(
            mode="PAPER",
            kite=None,
            config_capital=500000.0,
        )
        
        assert isinstance(provider, ConfigCapitalProvider)
        assert provider.get_available_capital() == 500000.0

    def test_create_live_mode_provider(self):
        """Test creating provider for LIVE mode builds Kite client from env."""
        mock_kite = MagicMock()
        
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.return_value = mock_kite
            mock_kite.margins.return_value = {"net": 500000.0}
            
            provider = create_capital_provider(
                mode="LIVE",
                config_capital=500000.0,
            )
            
            assert isinstance(provider, LiveCapitalProvider)

    def test_create_live_mode_falls_back_without_kite(self):
        """Test creating provider for LIVE mode without Kite client falls back to config."""
        with patch("core.capital_provider.make_kite_client_from_env") as mock_make:
            mock_make.side_effect = Exception("No token")
            
            provider = create_capital_provider(
                mode="LIVE",
                kite=None,  # No Kite client
                config_capital=500000.0,
            )
            
            # Should fall back to ConfigCapitalProvider
            assert isinstance(provider, ConfigCapitalProvider)
            assert provider.get_available_capital() == 500000.0

    def test_create_with_case_insensitive_mode(self):
        """Test mode parameter is case-insensitive."""
        provider1 = create_capital_provider(mode="paper", config_capital=100000.0)
        provider2 = create_capital_provider(mode="PAPER", config_capital=100000.0)
        provider3 = create_capital_provider(mode="Paper", config_capital=100000.0)
        
        assert isinstance(provider1, ConfigCapitalProvider)
        assert isinstance(provider2, ConfigCapitalProvider)
        assert isinstance(provider3, ConfigCapitalProvider)


class TestCapitalProviderIntegration:
    """Integration tests for capital provider usage."""

    def test_capital_provider_with_portfolio_state(self):
        """Test using capital provider to build portfolio state."""
        from risk.position_sizer import PortfolioState
        
        provider = ConfigCapitalProvider(500000.0)
        capital = provider.get_available_capital()
        
        state = PortfolioState(
            capital=capital,
            equity=capital,
            total_notional=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            free_notional=capital,
            open_positions=0,
            positions={},
        )
        
        assert state.capital == 500000.0
        assert state.equity == 500000.0
