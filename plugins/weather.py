"""
Sample Plugin: Weather

Demonstrates a plugin that provides weather information.
"""

from plugins import Plugin, PluginMetadata


class WeatherPlugin(Plugin):
    """A plugin that provides weather information."""
    
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="WeatherPlugin",
            version="1.0.0",
            description="Provides current weather information",
            author="JARVIS Team",
            permissions=["network"],
            plugin_type="tool"
        )
    
    def on_load(self) -> bool:
        logger = self.context.get("logger")
        if logger:
            logger.info("Weather plugin loaded successfully")
        return True
    
    def on_unload(self) -> None:
        logger = self.context.get("logger")
        if logger:
            logger.info("Weather plugin unloaded")
    
    def register_tools(self) -> dict:
        return {
            "get_weather": self.get_weather,
            "get_forecast": self.get_forecast,
        }
    
    def get_weather(self, plan: dict) -> str:
        """Get current weather for a location."""
        city = plan.get("city", "your location")
        
        # In a real implementation, you'd call a weather API
        # For demo purposes, return mock data
        speak = self.context.get("speak")
        if speak:
            speak(f"Checking weather for {city}, sir.")
        
        return f"The weather in {city} is currently 22 degrees Celsius and sunny, sir."
    
    def get_forecast(self, plan: dict) -> str:
        """Get weather forecast."""
        city = plan.get("city", "your location")
        days = plan.get("days", 3)
        
        return f"The {days}-day forecast for {city} shows sunny skies with highs around 24 degrees, sir."


# Plugin entry point - this is what the plugin manager looks for
PluginClass = WeatherPlugin